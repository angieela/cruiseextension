import re
from datetime import datetime


YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")


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


def format_sailing_date_range(start_date, end_date):
    """Format ISO start/end dates exactly as the extension formats a card."""
    if not start_date or not end_date:
        return None

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None

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
