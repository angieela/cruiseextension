import pytest

from date_utils import (
    build_sailing_identifier,
    format_sailing_date_range,
    parse_starting_date,
    parse_year,
)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("2027",), 2027),
        (("Sailings in 2028",), 2028),
        (("Jan 4 - Jan 11, 2027",), 2027),
        ((None, "valid for Sep 7, 2027"), 2027),
        (("Jan 4 - Jan 11", None), None),
    ],
)
def test_parse_year(values, expected):
    assert parse_year(*values) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Price valid for Sep 7, 2027", "Sep 7, 2027"),
        ("valid for Jan 1, 2028 per person", "Jan 1, 2028"),
        ("No qualifying disclosure", None),
        (None, None),
    ],
)
def test_parse_starting_date(text, expected):
    assert parse_starting_date(text) == expected


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2027-09-07", "2027-09-11", "Sep 7 - Sep 11"),
        ("2027-12-29", "2028-01-05", "Dec 29 - Jan 5"),
        ("not-a-date", "2027-09-11", None),
        (None, "2027-09-11", None),
        ("2027-09-07", None, None),
    ],
)
def test_format_sailing_date_range(start, end, expected):
    assert format_sailing_date_range(start, end) == expected


def test_build_sailing_identifier_rejects_missing_fields():
    assert build_sailing_identifier(None, "OV", "Sep 7 - Sep 11", "2027") is None
    assert build_sailing_identifier("PKG", None, "Sep 7 - Sep 11", "2027") is None
    assert build_sailing_identifier("PKG", "OV", None, "2027") is None
    assert build_sailing_identifier("PKG", "OV", "Sep 7 - Sep 11", None) is None
