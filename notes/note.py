#!/usr/bin/env python
import datetime as module_datetime
import enum
import functools
import json as module_json
import os
import pathlib
import sys
import zoneinfo
from typing import *

import pydantic
import typer
from yaml import safe_dump as dump_yaml, safe_load as load_yaml
from ruamel.yaml import YAML

PACIFIC = zoneinfo.ZoneInfo("America/Los_Angeles")

app = typer.Typer()


if "NOTES_PATH" in os.environ:
    DATA_PATH = pathlib.Path(os.environ["NOTES_PATH"]) / "data"
else:
    DATA_PATH = None


class TimeUnit(enum.Enum):
    HOUR = "hour"
    DAY = "day"
    BUSINESS_DAY = "business_day"
    WEEK = "week"
    MONTH = "month"


class NoteBaseModel(pydantic.BaseModel):
    notes: Optional[str] = None

    timestamp: module_datetime.datetime = pydantic.Field(
        default_factory=functools.partial(module_datetime.datetime.now, PACIFIC)
    )
    tags: List[str] = pydantic.Field(default_factory=list)

    def yaml(self):
        value = self.dict()
        return dump_yaml(value)

    @classmethod
    def parse_yaml(cls, serialized: str):
        value = load_yaml(serialized)
        return cls(**value)

    def load_path(self, file: pathlib.Path):
        if not file.exists():
            raise FileNotFoundError(f"{file} does not exist")
        serialized = file.read_text()
        return self.parse_yaml(serialized)

    @property
    def filename(self):
        return f"{self.timestamp.isoformat()}-{self.__class__.__name__.lower()}.yaml"

    def save(self, text=None, path: pathlib.Path = DATA_PATH):
        if path is None:
            raise ValueError("No path specified")
        path = path / self.filename
        if text is None:
            text = self.yaml()
        path.write_text(text)


class Prediction(NoteBaseModel):
    task: str

    time_unit: TimeUnit
    expected_completion: module_datetime.datetime | module_datetime.date
    std: Optional[float] = None
    range: Optional[Tuple[float, float]] = None



class Event(NoteBaseModel):
    event: str


@app.command()
def predict(data_dir=DATA_PATH):
    # Note: see https://yaml-multiline.info/
    prediction = Prediction()
    breakpoint()
    1 + 1


TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

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


@app.command()
def event(data_dir=DATA_PATH):
    event = Event.construct()
    template = TEMPLATES_DIR / "event.yaml"
    yaml_obj = YAML()
    loaded = yaml_obj.load(template.read_text())
    loaded["timestamp"] = event.dict()["timestamp"]
    from io import StringIO
    s = StringIO()
    yaml_obj.dump(loaded, s)
    final = edit(s.getvalue())
    if final is not None:
        # TODO: validate show another editor window with the errors.
        event = Event.parse_yaml(final)
        event.save(final)
        print(f"Event saved to {event.filename}")
    else:
        print("No changes made to template; aborting.")
        sys.exit(1)



@app.command()
def foo(bar: int):
    print("foo", bar)


@app.command()
def bar(bar: str, baz: bool=False):
    if baz:
        print("foo", bar, baz)


if __name__ == '__main__':
    app()