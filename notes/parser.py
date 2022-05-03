import datetime
import hashlib
import pathlib
import zoneinfo
import os

import commonmark
from dateutil.relativedelta import relativedelta
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
    "hour": (lambda x: datetime.timedelta(hours=int(x))),
    "day": (lambda x: datetime.timedelta(days=int(x))),
    "week": (lambda x: datetime.timedelta(weeks=int(x))),
    "year": (lambda x: relativedelta(years=int(x))),

    "month": (lambda x: relativedelta(months=int(x))),
    "business day": parse_bday,
}


def parse_datetime_or_delta(
    s: str | datetime.datetime | datetime.date | None,
    ts: datetime.datetime | datetime.date,
) -> datetime.datetime | datetime.date:
    if not isinstance(s, str) or not s:
        return s
    if s.lower() == "never":
        return datetime.date(2100, 1, 1)
    elif re.fullmatch(r"\d{2}:\d{2}", s):
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



def parse_record(path: pathlib.Path) -> dict:
    ext = path.suffix
    extracts = {}
    orig = path.read_text()
    if ext == ".md":
        parsed = markdown_parser.parse(orig)
        nodes = list(parsed.walker())
        heading = next(n[0] for n in nodes if n[0].t == "heading" and n[0].level == 1)
        extracts["event"] = heading.first_child.literal
        metadata = next(n[0] for n in reversed(nodes) if n[0].t == "code_block" and n[0].info == "yaml")
        raw_data = yaml.load(metadata.literal)
    elif ext == ".yaml":
        raw_data = yaml.load(path.read_text())
        extracts["event"] = raw_data["event"]
    else:
        raise ValueError(f"Unknown file type: {ext}")

    extracts["created"] = raw_data.get("date") or raw_data.get("timestamp")
    extracts["expected_completion"] = parse_datetime_or_delta(
        raw_data.get("expected_completion"), extracts["created"])
    extracts["due"] = parse_datetime_or_delta(raw_data.get("due"), extracts["created"])
    relative_to_date = (
        extracts["expected_completion"] or extracts["due"] or extracts["created"] or datetime.date.today())

    if raw_data.get("irrelevant_after"):
        irrelevant = parse_datetime_or_delta(raw_data["irrelevant_after"], relative_to_date)
    else:
        irrelevant = extracts["created"] + datetime.timedelta(days=365)
    extracts["irrelevant"] = irrelevant


    extracts["completed"] = raw_data.get("completed")
    extracts["completed_at"] = parse_datetime_or_delta(raw_data.get("completed_at"), relative_to_date)
    extracts["tags"] = raw_data.get("tags", [])
    extracts["file"] = path
    extracts["raw_data"] = raw_data
    [type] = re.findall(r'[0-9T:.-]+-(.*)', path.stem)
    extracts["type"] = type
    extracts["file_id"] = file_id(path)
    extracts["path"] = path
    return extracts


def file_id(path):
    if isinstance(path, str):
        path = pathlib.Path(path)
    return hashlib.blake2s(path.name.encode()).hexdigest()[:10]


def parsed_tasks(glob: str, data_dir: pathlib.Path) -> list[dict]:
    for path in data_dir.glob(glob):
        try:
            yield parse_record(path)
        except Exception as e:
            print(f"Error parsing {path}: {e}")