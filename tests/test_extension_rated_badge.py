import json
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app, get_db
from backend.models import Cruise, PriceHistory


CONTENT_SCRIPT = Path(__file__).resolve().parents[1] / "extension" / "content.js"
HISTORICAL_PRICES = [800.0, 900.0, 1000.0, 1100.0, 1200.0]


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def add_sailing_with_five_daily_prices(db_session):
    cruise = Cruise(
        package_code="LE07M870",
        ship_code="LE",
        ship_name="Legend of the Seas",
        itinerary_name="Western Mediterranean Cruise",
        year=2027,
        start_date=date(2027, 10, 3),
        end_date=date(2027, 10, 10),
        date_range="Oct 3 - Oct 10",
    )
    db_session.add(cruise)
    db_session.flush()

    first_scrape_day = date(2026, 9, 1)
    for offset, price in enumerate(HISTORICAL_PRICES):
        db_session.add(
            PriceHistory(
                cruise_id=cruise.id,
                date_scraped=first_scrape_day + timedelta(days=offset),
                price=price,
            )
        )
    db_session.commit()
    return cruise


def render_rating_badge(rating):
    if shutil.which("node") is None:
        pytest.skip("Node.js is required to execute the real content script")

    script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const rating = JSON.parse(process.argv[2]);
const content = {
  children: [],
  replaceChildren(...elements) { this.children = elements; },
};
const sandbox = {
  console: { log() {}, warn() {}, error() {} },
  chrome: { runtime: { sendMessage: async () => ({ status: 404 }) } },
  window: { clearTimeout() {}, setTimeout() {} },
  document: {
    documentElement: {},
    querySelector(selector) {
      return selector === "#cruiseka-rating-widget .cruiseka-rating-content"
        ? content
        : null;
    },
    querySelectorAll() { return []; },
    createElement() { return { className: "", textContent: "", style: {} }; },
  },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
vm.runInContext("renderWidgetState", sandbox)("rating", rating);
process.stdout.write(JSON.stringify(content.children.map((element) => ({
  className: element.className,
  textContent: element.textContent,
}))));
"""
    result = subprocess.run(
        ["node", "-e", script, str(CONTENT_SCRIPT), json.dumps(rating)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    (
        "live_price",
        "expected_discount",
        "expected_signed_percentage",
        "expected_label",
        "expected_emoji",
        "expected_badge_text",
    ),
    [
        (650.0, 35.0, "+35.00%", "Really Great Deal", "🤩", [
            "Current: $650", "35.00% below average", "🤩 Really Great Deal"
        ]),
        (750.0, 25.0, "+25.00%", "Great Deal", "🔥", [
            "Current: $750", "25.00% below average", "🔥 Great Deal"
        ]),
        (1100.0, -10.0, "-10.00%", "Not the Best", "👎", [
            "Current: $1,100", "10.00% above average", "👎 Not the Best"
        ]),
    ],
)
def test_five_days_reach_and_render_rated_badge(
    client,
    db_session,
    live_price,
    expected_discount,
    expected_signed_percentage,
    expected_label,
    expected_emoji,
    expected_badge_text,
):
    cruise = add_sailing_with_five_daily_prices(db_session)

    response = client.get(
        "/cruise-rating",
        params={
            "package_code": cruise.package_code,
            "ship_code": cruise.ship_code,
            "sailing_date_range": cruise.date_range,
            "year": cruise.year,
            "current_price": live_price,
        },
    )

    assert response.status_code == 200
    rating = response.json()
    assert rating["status"] == "rated"
    assert rating["average_price"] == 1000.0
    assert rating["current_price"] == live_price
    assert rating["discount_percent"] == expected_discount
    assert rating["signed_percentage"] == expected_signed_percentage
    assert rating["label"] == expected_label
    assert rating["emoji"] == expected_emoji

    badge_elements = render_rating_badge(rating)
    assert [element["textContent"] for element in badge_elements] == expected_badge_text
