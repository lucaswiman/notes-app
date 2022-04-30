import datetime
import pathlib
import zoneinfo
import os

import commonmark
import regex as re
from ruamel.yaml import YAML

yaml = YAML(typ="safe")

markdown_parser = commonmark.Parser()


TIMEZONE = zoneinfo.ZoneInfo(os.environ.get("NOTES_TIMEZONE", "America/Los_Angeles"))


def parse_bday(bday: str):
    # Inline import because pandas is pretty slow to import.
    from pandas.tseries.offsets import BDay
    return BDay(int(bday))


TIME_UNITS = {
    "hour": (lambda x: datetime.timedelta(hours=x)),
    "day": (lambda x: datetime.timedelta(days=int(x))),
    "week": (lambda x: datetime.timedelta(weeks=int(x))),

    # TODO: some months are not 30 days long.
    "month": (lambda x: datetime.timedelta(days=int(x)*30)),
    "business day": parse_bday,
}


def parse_datetime_or_delta(
    s: str | datetime.datetime | datetime.date,
    ts: datetime.datetime
) -> datetime.datetime | datetime.date:
    if not isinstance(s, str):
        return s
    if re.fullmatch(r"\d{2}:\d{2}", s):
        time = datetime.datetime.strptime(s, "%H:%M", tzinfo=TIMEZONE).time()
        return ts.replace(hour=time.hour, minute=time.minute, second=0, microsecond=0)
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2} (am|pm)", s):
        return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M %p', tzinfo=TIMEZONE)
    elif (m := re.fullmatch(r"(\d+) (\L<formats>)s?", s, formats=list(TIME_UNITS))):
        unit = m.group(2)
        result = ts + TIME_UNITS[unit](m.group(1))
        if unit != "hour" and hasattr(result, "date"):
            result = result.date()
        return result
    else:
        raise ValueError(f"Unrecognized format: {s}.")



def parse(path: pathlib.Path) -> dict:
    ext = path.suffix
    if ext == ".md":
        ast = markdown_parser.parse(path.read_text())
        nodes = list(ast.walker())
        heading = next(n[0] for n in nodes if n[0].t == "heading" and n[0].level == 1)
        title = heading.first_child.literal
        metadata = next(n[0] for n in reversed(nodes) if n[0].t == "code_block" and n[0].info == "yaml")
        value = yaml.load(metadata.literal)
        date = value.get("date") or datetime.date.today()
        if value.get("irrelevant_after"):
            if value.get("irrelevant_after") == "never":
                irrelevant = datetime.date(2100, 1, 1)
            else:
                irrelevant = parse_datetime_or_delta(value["irrelevant_after"], date)
        else:
            irrelevant = date + datetime.timedelta(year=1)
    elif ext == ".yaml":
        raise NotImplementedError() # TODO
    else:
        raise ValueError(f"Unknown file type: {ext}")
    loaded = yaml_obj.load(path.read_text())
