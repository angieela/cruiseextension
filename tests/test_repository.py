from datetime import date

import pytest

from models import Cruise, PriceHistory
from repository import save_scraped_rows


def make_row(**overrides):
    row = {
        "date_scraped": "2027-01-01",
        "itinerary_name": "Hawaii Cruise",
        "length": "7 Nights",
        "ship_name": "Ovation of the Seas",
        "package_code": "OV07HNL-001",
        "ship_code": "OV",
        "sailing_date_range": "Sep 7 - Sep 14",
        "year": 2027,
        "price": "$1,200",
        "departure_port": "Honolulu, Hawaii",
        "ports": "Honolulu, Maui, Hilo",
    }
    row.update(overrides)
    return row


def test_creates_cruise_and_price_record(db_session):
    summary = save_scraped_rows(db_session, [make_row()])

    assert summary == {
        "cruises_created": 1,
        "inserted": 1,
        "updated": 0,
        "skipped": 0,
    }
    assert db_session.query(Cruise).count() == 1
    assert db_session.query(PriceHistory).count() == 1
    assert db_session.query(PriceHistory).one().price == 1200.0


def test_same_cruise_identity_does_not_create_second_cruise(db_session):
    save_scraped_rows(db_session, [make_row()])
    summary = save_scraped_rows(
        db_session,
        [make_row(date_scraped="2027-01-02", itinerary_name="Updated name")],
    )

    assert summary["cruises_created"] == 0
    assert db_session.query(Cruise).count() == 1
    assert db_session.query(Cruise).one().itinerary_name == "Updated name"


def test_same_sailing_and_day_updates_but_different_day_inserts(db_session):
    save_scraped_rows(db_session, [make_row(price=1200)])
    same_day = save_scraped_rows(db_session, [make_row(price=950)])

    assert same_day["updated"] == 1
    assert same_day["inserted"] == 0
    assert db_session.query(PriceHistory).count() == 1
    assert db_session.query(PriceHistory).one().price == 950.0

    next_day = save_scraped_rows(
        db_session,
        [make_row(date_scraped="2027-01-02", price=900)],
    )

    assert next_day["inserted"] == 1
    assert next_day["updated"] == 0
    assert db_session.query(PriceHistory).count() == 2
    assert {row.date_scraped for row in db_session.query(PriceHistory)} == {
        date(2027, 1, 1),
        date(2027, 1, 2),
    }


def test_allows_multiple_sailing_ranges_for_one_cruise(db_session):
    summary = save_scraped_rows(
        db_session,
        [
            make_row(sailing_date_range="Sep 7 - Sep 14"),
            make_row(sailing_date_range="Sep 14 - Sep 21", price=1300),
        ],
    )

    assert summary["cruises_created"] == 1
    assert summary["inserted"] == 2
    assert db_session.query(Cruise).count() == 1
    assert db_session.query(PriceHistory).count() == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"price": "Call for price"},
        {"package_code": None},
        {"ship_code": None},
        {"sailing_date_range": None},
    ],
)
def test_skips_invalid_prices_and_missing_identifiers(db_session, overrides):
    summary = save_scraped_rows(db_session, [make_row(**overrides)])

    assert summary["skipped"] == 1
    assert summary["inserted"] == 0
    assert db_session.query(Cruise).count() == 0
    assert db_session.query(PriceHistory).count() == 0


def test_rolls_back_all_changes_after_unexpected_failure(db_session):
    invalid_row = make_row()
    invalid_row.pop("date_scraped")

    with pytest.raises(KeyError):
        save_scraped_rows(db_session, [make_row(), invalid_row])

    assert db_session.query(Cruise).count() == 0
    assert db_session.query(PriceHistory).count() == 0
