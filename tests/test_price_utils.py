import math

import pytest

from price_utils import parse_price


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("$1,299", 1299.0),
        ("USD 999.50", 999.5),
        ("from $799", 799.0),
        (1200, 1200.0),
        (0, 0.0),
        (None, None),
        ("", None),
        ("Call for price", None),
        (-10, None),
        (True, None),
        (math.nan, None),
        (math.inf, None),
    ],
)
def test_parse_price(value, expected):
    assert parse_price(value) == expected
