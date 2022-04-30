#!/usr/bin/env python
import datetime as module_datetime
import hashlib
import itertools
import os
import pathlib
import regex as re
import sys
import tempfile
import zoneinfo
from subprocess import call
from typing import Optional

import tabulate
import typer

from ruamel.yaml import YAML


app = typer.Typer()


if "NOTES_PATH" in os.environ:
    DATA_PATH = pathlib.Path(os.environ["NOTES_PATH"]) / "data"
else:
    DATA_PATH = None

if "NOTES_TEMPLATE_PATH" in os.environ:
    TEMPLATE_PATH = pathlib.Path(os.environ["NOTES_TEMPLATE_PATH"])
else:
    TEMPLATE_PATH = pathlib.Path(__file__).parent / "templates"

TIMEZONE = zoneinfo.ZoneInfo(os.environ.get("NOTES_TIMEZONE", "America/Los_Angeles"))

TEMPLATES = list(itertools.chain(TEMPLATE_PATH.glob("*.md"), TEMPLATE_PATH.glob("*.txt"), TEMPLATE_PATH.glob("*.yaml")))

COMMAND_TO_TEMPLATE = {f.stem.replace('-', '_'): f for f in TEMPLATES}


def show_table(table_data: list, headers: list, show_index=True, pickable=False, edit=False, data_dir=DATA_PATH):
    table = tabulate.tabulate(table_data, headers=headers, showindex=show_index)
    if pickable:
        from pick import pick
        rows = table.split('\n')
        title = '\n'.join(['  ' + rows[0], '  ' + rows[1]])
        rows = rows[2:]
        row, idx = pick(rows, title)
        if edit:
            # TODO: assumes id is the last column.
            do_edit(id=table_data[idx][-1], data_dir=data_dir)
        return idx
    else:
        return print(table)


def edit_file(path: pathlib.Path):
    EDITOR = os.environ.get('EDITOR', 'vim')
    call([EDITOR, path])


def edit_template(text: str):
    with tempfile.NamedTemporaryFile(suffix=".tmp", delete=True) as tf:
        tf.write(text.encode())
        tf.flush()
        edit_file(tf.name)
        edited_message = pathlib.Path(tf.name).read_text()
    if text == edited_message:
        return None
    else:
        return edited_message



def do_note(template: pathlib.Path, data_dir=DATA_PATH):
    timestamp = module_datetime.datetime.now(TIMEZONE)
    if template.suffix.lower() == ".yaml":
        yaml_obj = YAML()
        loaded = yaml_obj.load(template.read_text())
        loaded["timestamp"] = timestamp
        from io import StringIO
        s = StringIO()
        yaml_obj.dump(loaded, s)
        value = s.getvalue()
    else:
        value = template.read_text()
        from jinja2 import Environment, BaseLoader
        rtemplate = Environment(loader=BaseLoader).from_string(value)
        value = rtemplate.render(date=module_datetime.datetime.now(TIMEZONE).date().isoformat())
    final = edit_template(value)
    if final is not None:
        path = data_dir / f"{timestamp.year}/{timestamp.isoformat()}-{template.name}"
        path.write_text(final)

        # TODO: validate show another editor window with the errors.
        print(f"{template.stem.title()} saved to {path}")
    else:
        print("No changes made to template; aborting.")
        sys.exit(1)


record = typer.Typer()
app.add_typer(record, name="record", help="Make a new record of the given type.")
app.add_typer(record, name="mark", help="Alias of record.")


# TODO: how to define a command for each template in the directory without method each time?
@record.command()
def due_date(data_dir: pathlib.Path=DATA_PATH):
    return do_note(COMMAND_TO_TEMPLATE["due_date"], data_dir)


@record.command()
def event(data_dir: pathlib.Path=DATA_PATH):
    return do_note(COMMAND_TO_TEMPLATE["event"], data_dir)


@record.command()
def metric(data_dir: pathlib.Path=DATA_PATH):
    return do_note(COMMAND_TO_TEMPLATE["metric"], data_dir)


@record.command()
def note(data_dir: pathlib.Path=DATA_PATH):
    return do_note(COMMAND_TO_TEMPLATE["note"], data_dir)


@record.command()
def prediction(data_dir: pathlib.Path=DATA_PATH):
    return do_note(COMMAND_TO_TEMPLATE["prediction"], data_dir)


@record.command()
def task(data_dir: pathlib.Path=DATA_PATH):
    return do_note(COMMAND_TO_TEMPLATE["task"], data_dir)


def parse_bday(bday: str):
    # Inline import because pandas is pretty slow to import.
    from pandas.tseries.offsets import BDay
    return BDay(int(bday))


TIME_UNITS = {
    "hour": (lambda x: module_datetime.timedelta(hours=x)),
    "day": (lambda x: module_datetime.timedelta(days=int(x))),
    "week": (lambda x: module_datetime.timedelta(weeks=int(x))),

    # TODO: some months are not 30 days long.
    "month": (lambda x: module_datetime.timedelta(days=int(x)*30)),
    "business day": parse_bday,
}

def is_date(d):
    return isinstance(d, module_datetime.date) and not isinstance(d, module_datetime.datetime)


def dt_compare(d1, d2):
    if is_date(d1) and not is_date(d2):
        d2 = d2.date()
    elif is_date(d2) and not is_date(d1):
        d1 = d1.date()
    return d1 <= d2

def parse_datetime_or_delta(
    s: str | module_datetime.datetime | module_datetime.date,
    ts: module_datetime.datetime
) -> module_datetime.datetime | module_datetime.date:
    if not isinstance(s, str):
        return s
    if re.fullmatch(r"\d{2}:\d{2}", s):
        time = module_datetime.datetime.strptime(s, "%H:%M", tzinfo=TIMEZONE).time()
        return ts.replace(hour=time.hour, minute=time.minute, second=0, microsecond=0)
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return module_datetime.datetime.strptime(s, "%Y-%m-%d").date()
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2} (am|pm)", s):
        return module_datetime.datetime.strptime(s, '%Y-%m-%d %H:%M %p', tzinfo=TIMEZONE)
    elif (m := re.fullmatch(r"(\d+) (\L<formats>)s?", s, formats=list(TIME_UNITS))):
        unit = m.group(2)
        result = ts + TIME_UNITS[unit](m.group(1))
        if unit != "hour" and hasattr(result, "date"):
            result = result.date()
        return result
    else:
        raise ValueError(f"Unrecognized format: {s}.")


query = typer.Typer()
app.add_typer(query, name="query", help="Commands to query records.")
app.add_typer(query, name="list", help="Alias of query.")


def file_id(path):
    if isinstance(path, str):
        path = pathlib.Path(path)
    return hashlib.blake2s(path.name.encode()).hexdigest()[:10]


@query.command()
def tasks(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False, edit: bool=False):
    """
    Show all tasks from task and due dates.

    If --show-all is selected, then expired or completed tasks will be included.
    """
    yaml = YAML(typ="safe")
    now = module_datetime.datetime.now(tz=TIMEZONE)
    table = []
    for task in data_dir.glob("**/*.yaml"):
        if task.stem.endswith("task") or task.stem.endswith("due-date"):
            value = yaml.load(task)
            ts = value["timestamp"]
            due_str = value.get("due")
            if due_str is not None:
                due = parse_datetime_or_delta(due_str, ts)
                irrelevancy_start = due
            else:
                due = ''
                irrelevancy_start = ts
            irrelevant = parse_datetime_or_delta(value["irrelevant_after"], irrelevancy_start)
            completed = value.get("completed")
            if show_all or (not completed and dt_compare(now, irrelevant)):
                table.append((
                    due.isoformat() if hasattr(due, "isoformat") else due,
                    value['event'],
                    ts.date().isoformat(),
                    bool(completed),
                    file_id(task)))
    table.sort(key=lambda x: x[0], reverse=False)
    show_table(
        table,
        headers=["Due", "Task", "Created", "Completed", "id"],
        pickable=edit,
        edit=edit,
        data_dir=data_dir,
    )


@query.command()
def predictions(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False):
    """
    Query predictions and due dates.

    If --show-all is selected, then completed predictions will be included.
    """
    yaml = YAML(typ="safe")
    table = []
    for task in data_dir.glob("**/*.yaml"):
        if task.stem.endswith("prediction"):
            value = yaml.load(task)
            ts = value["timestamp"]
            expectation_str = value.get("expected_completion")
            expectation = None
            if expectation_str is not None:
                expectation = parse_datetime_or_delta(expectation_str, ts)
            completed_at = value.get("completed_at")
            if show_all or not completed_at:
                table.append((
                    expectation.isoformat(),
                    value['event'],
                    ts.date().isoformat(),
                    completed_at.isoformat() if completed_at else None,
                    file_id(task))
                )
    table.sort(key=lambda x: x[0], reverse=False)
    show_table(table, headers=["Expected Completion", "Event", "Created", "Actual", "id"])


@query.command()
def notes(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False, tag=None, edit: bool=False):
    import commonmark
    parser = commonmark.Parser()
    yaml = YAML(typ="safe")
    table = []
    for file in data_dir.glob("**/*.md"):
        if file.stem.endswith("note"):
            ast = parser.parse(file.read_text())
            nodes = list(ast.walker())
            heading = next(n[0] for n in nodes if n[0].t == "heading" and n[0].level == 1)
            title = heading.first_child.literal
            metadata = next (n[0] for n in reversed(nodes) if n[0].t == "code_block" and n[0].info == "yaml")
            value = yaml.load(metadata.literal)
            date = value.get("date") or module_datetime.date.today()
            if value.get("irrelevant_after"):
                if value.get("irrelevant_after") == "never":
                    irrelevant = module_datetime.date(2100, 1, 1)
                else:
                    irrelevant = parse_datetime_or_delta(value["irrelevant_after"], date)
            else:
                irrelevant = date + module_datetime.timedelta(year=1)
            tags = value.get("tags", [])
            if not (tag is None or tag in tags):
                continue
            completed = value.get("completed")
            if show_all or (not completed and dt_compare(module_datetime.datetime.now(), irrelevant)):
                table.append((
                    date.isoformat(),
                    title,
                    ", ".join(tags),
                    file_id(file),
                ))
    table.sort(key=lambda x: x[0], reverse=False)
    show_table(table, headers=["Date", "Note", "tags", "id"], pickable=edit, edit=edit)


def by_id(data_dir: pathlib.Path=DATA_PATH, id: str=None) -> pathlib.Path:
    """
    Query by id.
    """
    for file in data_dir.glob("**/*.*"):
        if id == file.name or id == file_id(file):
            return file

def cmd_by_id(default: str, data_dir: pathlib.Path=DATA_PATH, id: str=None, env_variable: Optional[str]=None):
    cmd = os.environ.get(env_variable, default)
    file = by_id(data_dir, id)
    if id is None:
        print(f"No file found with id {id}")
        sys.exit(1)
    else:
        call([cmd, str(file)])

@app.command(help="Edit a record by id.", name="edit")
@query.command(help="Edit a record by id.", name="edit")
def do_edit(id: str, data_dir: pathlib.Path=DATA_PATH):
    cmd_by_id("vim", data_dir, id, "EDITOR")


@app.command(help="View record by id (with PAGER).")
@query.command(help="View record by id (with PAGER).")
def view(id: str, data_dir: pathlib.Path=DATA_PATH):
    cmd_by_id("less", data_dir, id, "PAGER")


@record.command(help="Mark a task, due date or prediction as complete.")
def complete(id: str, completed_at=None, data_dir: pathlib.Path=DATA_PATH):
    if completed_at is None:
        completed_at = module_datetime.datetime.now(tz=TIMEZONE)
    else:
        completed_at = parse_datetime_or_delta(completed_at, module_datetime.datetime.now(tz=TIMEZONE))
    for task in data_dir.glob("**/*.*"):
        if id == task.name or id == file_id(task):
            yaml = YAML(typ="safe")
            value = yaml.load(task)
            value["completed_at"] = completed_at
            value["completed"] = True
            yaml.dump(value, task)
            return


@query.command(help="Search records for a given string.")
def grep(string: str, data_dir: pathlib.Path=DATA_PATH, edit=False):
    """
    TODO: should we just defer this entirely to grep, like git-grep, then display the match
          in our tabular format.
    """
    data = []
    for task in data_dir.glob("**/*.*"):
        if string in task.read_text():
            data.append((task.name, file_id(task)))
    show_table(data, headers=["Name", "id"], edit=edit, pickable=edit)


if __name__ == '__main__':
    app()