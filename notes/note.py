#!/usr/bin/env python
import datetime as module_datetime
import itertools
import os
import pathlib
import sys
import zoneinfo

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


def edit(text: str):
    import sys, tempfile, os
    from subprocess import call

    EDITOR = os.environ.get('EDITOR', 'vim')


    with tempfile.NamedTemporaryFile(suffix=".tmp", delete=True) as tf:
        tf.write(text.encode())
        tf.flush()
        call([EDITOR, tf.name])
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
    final = edit(value)
    if final is not None:
        path = data_dir / f"{timestamp.year}/{timestamp.isoformat()}-{template.name}"
        path.write_text(final)

        # TODO: validate show another editor window with the errors.
        print(f"{template.stem.title()} saved to {path}")
    else:
        print("No changes made to template; aborting.")
        sys.exit(1)


record = typer.Typer()
app.add_typer(record, name="record")


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


query = typer.Typer()
app.add_typer(query, name="query")

@query.command()
def tasks(data_dir: pathlib.Path=DATA_PATH, show_all: bool=False):
    """
    Show all tasks from task and due dates.

    If --show-all is selected, then expired or completed tasks will be included.
    """
    yaml = YAML(typ="safe")
    for task in data_dir.glob("**/*.yaml"):
        if task.stem.endswith("task") or task.stem.endswith("due_date"):
            value = yaml.load(task)
            breakpoint()
            # if show_all or not task.stem.endswith("_completed"):
            #     print(task.read_text())
    raise NotImplementedError()


if __name__ == '__main__':
    app()