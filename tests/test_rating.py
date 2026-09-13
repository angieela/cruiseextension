import pytest

from main import get_price_rating


@pytest.mark.parametrize(
    ("discount", "expected"),
    [
        (30, ("Really Great Deal", "🤩")),
        (29.99, ("Great Deal", "🔥")),
        (20, ("Great Deal", "🔥")),
        (19.99, ("Good Deal", "👍")),
        (5, ("Good Deal", "👍")),
        (4.99, ("Okay", "😐")),
        (-5, ("Okay", "😐")),
        (-5.01, ("Not the Best", "👎")),
        (-20, ("Not the Best", "👎")),
        (-20.01, ("Expensive", "💸")),
        (-30, ("Expensive", "💸")),
        (-30.01, ("Really Expensive", "🚨")),
    ],
)
def test_get_price_rating_boundaries(discount, expected):
    assert get_price_rating(discount) == expected
