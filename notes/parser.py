import datetime
import hashlib
import pathlib
import zoneinfo
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

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


# Matches date.weekday() behavior:
DAYS_OF_WEEK = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


SPECIAL_DAYS = {
    "today", "tomorrow", "yesterday",
    *DAYS_OF_WEEK.keys(),
    *["next %s" % day for day in DAYS_OF_WEEK.keys()],
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
    elif s.lower() in SPECIAL_DAYS:
        today = ts.date() if hasattr(ts, "date") else ts
        match s.lower().split():
            case ["today"]:
                return today
            case ["tomorrow"]:
                return today + datetime.timedelta(days=1)
            case ["yesterday"]:
                return today - datetime.timedelta(days=-1)
            case ["next", day]:
                next_monday = today + datetime.timedelta(days=7 - today.weekday())
                return next_monday + datetime.timedelta(days=DAYS_OF_WEEK[day])
            case [day]:
                desired_day = DAYS_OF_WEEK[day]
                # "Monday" on Wednesday refers to two days previously.
                # "Friday" on a Wednesday refers to two days later.
                # "Next Friday" on a Wednesday refers to the following Friday (9 days later).
                return today + datetime.timedelta(days=desired_day - today.weekday())
        assert False, "unreachable"
    elif s.lower() == "tomorrow":
        return (ts.date() if hasattr(ts, "date") else ts) + datetime.timedelta(days=1)
    else:
        raise ValueError(f"Unrecognized format: {s}.")

def is_date(d):
    return isinstance(d, datetime.date) and not isinstance(d, datetime.datetime)


def dt_compare(d1, d2):
    if is_date(d1) and not is_date(d2):
        d2 = d2.date()
    elif is_date(d2) and not is_date(d1):
        d1 = d1.date()
    return d1 <= d2


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

    extracts["created"] = created =  raw_data.get("date") or raw_data.get("timestamp")
    if isinstance(created, datetime.datetime):
        # The yaml parser takes a timestamp like 2022-05-19 22:01:55.699594-07:00, and turns
        # it into a naive timestamp at UTC, like 2022-05-20T05:01:55.699594. So stupid, smdh.
        extracts["created"] = (
            datetime.datetime(*created.timetuple()[:6], tzinfo=datetime.timezone.utc)
            .astimezone(TIMEZONE)
        )

    extracts["expected_completion"] = parse_datetime_or_delta(
        raw_data.get("expected_completion"), extracts["created"])
    extracts["due"] = parse_datetime_or_delta(raw_data.get("due"), extracts["created"])
    relative_to_date = (
        extracts["expected_completion"] or extracts["due"] or extracts["created"] or datetime.date.today())

    for key in ["irrelevant_after", "irrelevant_before"]:
        irrelevant = None
        if (irrelevant := raw_data.get(key)):
            if irrelevant == '==due':
                irrelevant = extracts["due"]
            else:
                irrelevant = parse_datetime_or_delta(irrelevant, relative_to_date)
        elif key == "irrelevant_after":
            irrelevant = extracts["created"] + datetime.timedelta(days=365)
        extracts[key] = irrelevant

    now = datetime.datetime.now(tz=TIMEZONE)
    extracts["still_relevant"] = True
    if extracts["irrelevant_after"]:
        extracts["still_relevant"] = dt_compare(now, extracts["irrelevant_after"]) and extracts["still_relevant"]
    if extracts["irrelevant_before"]:
        extracts["still_relevant"] = dt_compare(extracts["irrelevant_before"], now) and extracts["still_relevant"]

    extracts["completed"] = raw_data.get("completed")
    extracts["completed_at"] = parse_datetime_or_delta(raw_data.get("completed_at"), relative_to_date)
    extracts["tags"] = raw_data.get("tags", [])
    extracts["file"] = path
    extracts["raw_data"] = raw_data
    [type] = re.findall(r'[0-9T:.-]+-(.*)', path.stem)
    extracts["type"] = type
    extracts["file_id"] = file_id(path)
    extracts["path"] = path
    extracts["rank_priority"] = raw_data.get('rank_priority', 10_000)

    return extracts


def file_id(path):
    if isinstance(path, str):
        path = pathlib.Path(path)
    return hashlib.blake2s(path.name.encode()).hexdigest()[:10]



def parsed_records(glob: str, data_dir: pathlib.Path) -> list[dict]:
    def do_parse(path):
        try:
            return parse_record(path)
        except Exception as e:
            import pdb; pdb.post_mortem()
            print(f"Failed to parse {path}: {e}")
    with ThreadPoolExecutor(max_workers=1) as ex:
        futures = [ex.submit(do_parse, path) for path in data_dir.glob(glob)]
        for fut in as_completed(futures):
            yield fut.result()
