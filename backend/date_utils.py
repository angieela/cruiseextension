import re
from datetime import date, datetime


YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
ISO_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:$|[T ])")


def parse_year(*values):
    """Return the first four-digit sailing year found in the supplied values."""
    for value in values:
        if value is None:
            continue

        match = YEAR_PATTERN.search(str(value))
        if match:
            return int(match.group(1))

    return None


def parse_starting_date(text):
    """Extract the date from Royal Caribbean's ``valid for`` disclosure."""
    if not text:
        return None

    match = re.search(r"valid for ([A-Za-z]{3} \d{1,2}, \d{4})", text)
    return match.group(1) if match else None


def normalize_sailing_date(value):
    """Return the source calendar date as ISO without timezone conversion."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None

    match = ISO_DATE_PATTERN.match(value.strip())
    if not match:
        return None

    try:
        return date.fromisoformat(match.group(1)).isoformat()
    except ValueError:
        return None


def format_sailing_date_range(start_date, end_date):
    """Format ISO start/end dates exactly as the extension formats a card."""
    normalized_start = normalize_sailing_date(start_date)
    normalized_end = normalize_sailing_date(end_date)
    if not normalized_start or not normalized_end:
        return None

    start = date.fromisoformat(normalized_start)
    end = date.fromisoformat(normalized_end)

    return f"{start:%b} {start.day} - {end:%b} {end.day}"


def build_sailing_identifier(
    package_code,
    ship_code,
    sailing_date_range,
    *year_sources,
):
    """Build the identifier persisted by the scraper and queried by the extension."""
    year = parse_year(*year_sources)
    if not package_code or not ship_code or not sailing_date_range or year is None:
        return None

    return {
        "package_code": package_code,
        "ship_code": ship_code,
        "sailing_date_range": sailing_date_range,
        "year": year,
    }
