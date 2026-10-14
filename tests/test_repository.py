from datetime import date

import pytest

from backend.models import Cruise, PriceHistory
from backend.repository import save_scraped_rows


def make_row(**overrides):
    row = {
        "date_scraped": "2027-01-01",
        "itinerary_name": "Hawaii Cruise",
        "length": "7 Nights",
        "ship_name": "Ovation of the Seas",
        "package_code": "OV07HNL-001",
        "ship_code": "OV",
        "start_date": "2027-09-07",
        "end_date": "2027-09-14",
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
    cruise = db_session.query(Cruise).one()
    assert cruise.id is not None
    assert cruise.package_code == "OV07HNL-001"
    assert cruise.ship_code == "OV"
    assert cruise.ship_name == "Ovation of the Seas"
    assert cruise.itinerary_name == "Hawaii Cruise"
    assert cruise.length == "7 Nights"
    assert cruise.year == 2027
    assert cruise.start_date == date(2027, 9, 7)
    assert cruise.end_date == date(2027, 9, 14)
    assert cruise.date_range == "Sep 7 - Sep 14"
    assert cruise.departure_port == "Honolulu, Hawaii"
    assert cruise.ports == "Honolulu, Maui, Hilo"
    assert cruise.created_at is not None
    assert cruise.updated_at is not None
    history = db_session.query(PriceHistory).one()
    assert history.id is not None
    assert history.date_scraped == date(2027, 1, 1)
    assert history.cruise_id == cruise.id
    assert history.price == 1200.0


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
    assert db_session.query(Cruise).count() == 1
    assert db_session.query(PriceHistory).count() == 2
    cruise_id = db_session.query(Cruise.id).scalar()
    assert {row.cruise_id for row in db_session.query(PriceHistory)} == {cruise_id}
    assert {row.date_scraped for row in db_session.query(PriceHistory)} == {
        date(2027, 1, 1),
        date(2027, 1, 2),
    }


def test_different_sailing_dates_create_separate_sailing_records(db_session):
    summary = save_scraped_rows(
        db_session,
        [
            make_row(sailing_date_range="Sep 7 - Sep 14"),
            make_row(
                start_date="2027-09-14",
                end_date="2027-09-21",
                sailing_date_range="Sep 14 - Sep 21",
                price=1300,
            ),
        ],
    )

    assert summary["cruises_created"] == 2
    assert summary["inserted"] == 2
    assert db_session.query(Cruise).count() == 2
    assert db_session.query(PriceHistory).count() == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"package_code": None},
        {"ship_code": None},
    ],
)
def test_skips_missing_identifiers(db_session, overrides):
    summary = save_scraped_rows(db_session, [make_row(**overrides)])

    assert summary["skipped"] == 1
    assert summary["inserted"] == 0
    assert db_session.query(Cruise).count() == 0
    assert db_session.query(PriceHistory).count() == 0


def test_malformed_dates_are_saved_as_null_without_dropping_sailing(db_session):
    summary = save_scraped_rows(
        db_session,
        [
            make_row(
                start_date="not-a-date",
                end_date=None,
                sailing_date_range=None,
                year=None,
            )
        ],
    )

    assert summary["inserted"] == 1
    assert summary["skipped"] == 0
    cruise = db_session.query(Cruise).one()
    assert cruise.start_date is None
    assert cruise.end_date is None
    assert cruise.date_range is None
    assert db_session.query(PriceHistory).count() == 1


def test_price_history_contains_only_price_observation_fields():
    columns = set(PriceHistory.__table__.columns.keys())

    assert columns == {"id", "date_scraped", "cruise_id", "price"}


def test_cruise_contains_all_sailing_metadata_fields():
    columns = set(Cruise.__table__.columns.keys())

    assert columns == {
        "id",
        "package_code",
        "ship_code",
        "ship_name",
        "itinerary_name",
        "length",
        "year",
        "start_date",
        "end_date",
        "date_range",
        "departure_port",
        "ports",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize("price", [None, "", "Call for price"])
def test_saves_missing_or_unrecognized_price_as_null(db_session, price):
    summary = save_scraped_rows(db_session, [make_row(price=price)])

    assert summary == {
        "cruises_created": 1,
        "inserted": 1,
        "updated": 0,
        "skipped": 0,
    }
    assert db_session.query(Cruise).count() == 1
    assert db_session.query(PriceHistory).count() == 1
    assert db_session.query(PriceHistory).one().price is None


def test_rolls_back_all_changes_after_unexpected_failure(db_session):
    invalid_row = make_row()
    invalid_row.pop("date_scraped")

    with pytest.raises(KeyError):
        save_scraped_rows(db_session, [make_row(), invalid_row])

    assert db_session.query(Cruise).count() == 0
    assert db_session.query(PriceHistory).count() == 0
