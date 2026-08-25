import math
import re


PRICE_PATTERNS = (
    re.compile(r"(?:\$|USD\s*)\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\bfrom\s+(?:\$|USD\s*)?\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"),
)


def parse_price(value):
    """Return a numeric price from common display text, or None if invalid."""
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        price = float(value)
        return price if math.isfinite(price) and price >= 0 else None

    text = str(value).strip()
    if not text:
        return None

    for pattern in PRICE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        try:
            price = float(match.group(1).replace(",", ""))
        except ValueError:
            continue

        if math.isfinite(price) and price >= 0:
            return price

    return None
