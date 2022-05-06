#!/usr/bin/env python
import datetime as module_datetime
import itertools
import os
import pathlib
import sys
import tempfile
from subprocess import call
from typing import Optional

import tabulate
import typer

from ruamel.yaml import YAML

from .parser import TIMEZONE, parsed_records, parse_datetime_or_delta, parse_record, file_id


app = typer.Typer()


if "NOTES_PATH" in os.environ:
    DATA_PATH = pathlib.Path(os.environ["NOTES_PATH"]) / "data"
else:
    DATA_PATH = None

if "NOTES_TEMPLATE_PATH" in os.environ:
    TEMPLATE_PATH = pathlib.Path(os.environ["NOTES_TEMPLATE_PATH"])
else:
    TEMPLATE_PATH = pathlib.Path(__file__).parent / "templates"


TEMPLATES = list(itertools.chain(TEMPLATE_PATH.glob("*.md"), TEMPLATE_PATH.glob("*.txt"), TEMPLATE_PATH.glob("*.yaml")))

COMMAND_TO_TEMPLATE = {f.stem.replace('-', '_'): f for f in TEMPLATES}


def show_table(table_data: list, headers: list, show_index=True, pickable=False, edit=False, cat=False, data_dir: pathlib.Path=DATA_PATH):
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
        if cat:
            file = by_id(id=table_data[idx][-1], data_dir=data_dir)
            print(file.read_text())
        return idx
    else:
        return print(table)


def edit_file(path: pathlib.Path):
    EDITOR = os.environ.get('EDITOR', 'vim')
    call([*EDITOR.split(), path])


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


def do_note(template: pathlib.Path, data_dir: pathlib.Path=DATA_PATH):
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
        print(f"{template.stem.title()} saved to {path} ({file_id(path)}).")
    else:
        print("No changes made to template; aborting.")
        sys.exit(1)


record = typer.Typer()
app.add_typer(record, name="record", help="Make a new record of the given type.")
app.add_typer(record, name="mark", help="Alias of record.")
app.add_typer(record, name="add", help="Alias of record.")


def do_template_command(command: str, data_dir: pathlib.Path=DATA_PATH):
    def _do_template(data_dir: pathlib.Path=data_dir):
        return do_note(COMMAND_TO_TEMPLATE[command], data_dir=data_dir)
    _do_template.__name__ = command
    return _do_template

for command in COMMAND_TO_TEMPLATE:
    method = do_template_command(command)
    record.command()(method)
    record.command(name=f"{command}s", help=f"Alias of {command}.", hidden=True)(method)


def is_date(d):
    return isinstance(d, module_datetime.date) and not isinstance(d, module_datetime.datetime)


def dt_compare(d1, d2):
    if is_date(d1) and not is_date(d2):
        d2 = d2.date()
    elif is_date(d2) and not is_date(d1):
        d1 = d1.date()
    return d1 <= d2


query = typer.Typer()
app.add_typer(query, name="query", help="Commands to query records.")
app.add_typer(query, name="list", help="Alias of query.")


@query.command()
@query.command(name="task", help="Alias of tasks.", hidden=True)
def tasks(data_dir: pathlib.Path=DATA_PATH, time_window: str="2 months", show_all: bool=False, edit: bool=False, created_on: Optional[str]=None):
    """
    Show all tasks from task and due dates.

    If --show-all is selected, then expired or completed tasks will be included.

    By default tasks due >2 months in the future will be excluded. To include them, use
    --time-window=never
    """
    now = module_datetime.datetime.now(tz=TIMEZONE)
    window = parse_datetime_or_delta(time_window, now)
    if created_on is not None:
        created_on = parse_datetime_or_delta(created_on, now)
    table = []
    for parsed in parsed_records("**/*.yaml", data_dir=data_dir):
        if parsed["type"] in ("task", "due-date") and (show_all or not parsed["completed_at"]):
            due = parsed.get("due")
            completed = parsed.get("completed")
            if show_all or (not completed and dt_compare(now, parsed.get("irrelevant"))):
                if ((not due or dt_compare(due, window))
                        and (not created_on or parsed["created"].date() == created_on)):
                    table.append((
                        (due.isoformat() if hasattr(due, "isoformat") else due) or "",
                        parsed['event'],
                        parsed["created"].date().isoformat(),
                        bool(completed),
                        parsed["file_id"]))
    table.sort(key=lambda x: x[0], reverse=False)
    show_table(
        table,
        headers=["Due", "Task", "Created", "Completed", "id"],
        pickable=edit,
        edit=edit,
        data_dir=data_dir,
    )


@query.command()
def predictions(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False, edit: bool=False):
    """
    Query predictions and due dates.

    If --show-all is selected, then completed predictions will be included.
    """
    table = []
    for parsed in parsed_records("**/*.yaml", data_dir=data_dir):
        if parsed["type"] == "prediction" and (show_all or not parsed["completed_at"]):
            table.append((
                parsed["expected_completion"].isoformat(),
                parsed["event"],
                parsed["created"].date().isoformat(),
                parsed["completed_at"],
                parsed["file_id"],
            ))

    table.sort(key=lambda x: x[0], reverse=False)
    show_table(table, headers=["Expected Completion", "Event", "Created", "Actual", "id"],
               edit=edit, data_dir=data_dir, pickable=edit)


def list_md(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False, edit: bool=False, suffix="note", tag=None, cat=False):
    table = []
    for parsed in parsed_records(f"**/*-{suffix}.md", data_dir=data_dir):
        if parsed["type"] == suffix:
            completed = parsed["completed"]
            irrelevant = parsed["irrelevant"]
            title = parsed["event"]
            date = parsed["created"]
            if show_all or (not completed and dt_compare(module_datetime.datetime.now(), irrelevant)):
                if tag is None or tag in parsed["tags"]:
                    table.append((
                        date.isoformat(),
                        title,
                        ", ".join(parsed["tags"]),
                        parsed["file_id"],
                    ))
    table.sort(key=lambda x: x[0], reverse=False)
    show_table(table, headers=["Date", "Title", "tags", "id"], pickable=edit or cat, edit=edit, cat=cat)


@query.command(help="List all notes.")
def notes(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False, edit: bool=False,
          tag: Optional[str]=None, cat: bool=False):
    """
    List all notes.

    If --show-all is selected, then completed notes will be included.
    """
    return list_md(data_dir=data_dir, show_all=show_all, edit=edit, suffix="note", tag=tag, cat=cat)


@query.command(help="List all gists.")
def gists(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False, edit: bool=False,
          tag: Optional[str]=None, cat: bool=False):
    """
    List all notes.

    If --show-all is selected, then completed notes will be included.
    """
    return list_md(data_dir=data_dir, show_all=show_all, edit=edit, suffix="gist", tag=tag, cat=cat)



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
        call([*cmd.split(), str(file)])

@app.command(help="Edit a record by id.", name="edit")
@query.command(help="Edit a record by id.", name="edit")
def do_edit(id: str, data_dir: pathlib.Path=DATA_PATH):
    cmd_by_id("vim", data_dir, id, "EDITOR")


@app.command(help="View record by id (with PAGER).")
@query.command(help="View record by id (with PAGER).")
def view(id: str, data_dir: pathlib.Path=DATA_PATH):
    cmd_by_id("less", data_dir, id, "PAGER")


@app.command(help="Print record by id.")
@query.command(help="Print record by id.")
def cat(id: str, data_dir: pathlib.Path=DATA_PATH):
    cmd_by_id("cat", data_dir, id, "PRINTER")


@record.command(help="Mark a task, due date or prediction as complete.")
@app.command(name="complete", help="Alias of `record complete`.", hidden=True)
def complete(id: Optional[str] = None, completed_at=None, data_dir: pathlib.Path=DATA_PATH):
    # TODO: (1) make this work for notes.
    # TODO: (2) make this pickable.
    if completed_at is None:
        completed_at = module_datetime.datetime.now(tz=TIMEZONE)
    else:
        completed_at = parse_datetime_or_delta(completed_at, module_datetime.datetime.now(tz=TIMEZONE))
    def do_complete(file: pathlib.Path):
        yaml = YAML(typ="safe")
        value = yaml.load(file)
        value["completed_at"] = completed_at
        value["completed"] = True
        yaml.dump(value, file)

    if id:
        for task in data_dir.glob("**/*.*"):
            if id == task.name or id == file_id(task):
                do_complete(task)
                return
    else:
        table = [
            (parsed["created"].date(), parsed["type"], parsed["due"], parsed["event"], parsed["file_id"])
            for parsed in parsed_records("**/*.yaml", data_dir=data_dir)
            if "completed" in parsed and not parsed["completed"]
        ]
        row_num = show_table(table, headers=["created", "type", "due", "event", "id"], edit=False, pickable=True)
        row = table[row_num]
        do_complete(by_id(row[-1]))


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