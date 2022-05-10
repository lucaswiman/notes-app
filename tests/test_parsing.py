import datetime
from notes.parser import parse_datetime_or_delta

def test_parse_datetime_or_delta():
    assert parse_datetime_or_delta('next thursday', datetime.date(2022, 5, 3)) == datetime.date(2022, 5, 12)
    assert parse_datetime_or_delta('thursday', datetime.date(2022, 5, 3)) == datetime.date(2022, 5, 5)
