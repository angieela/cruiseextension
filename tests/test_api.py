from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app, get_db
from models import Cruise, PriceHistory


SAILING_RANGE = "Sep 7 - Sep 14"
YEAR = 2027


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


def add_cruise(db_session):
    cruise = Cruise(
        package_code="OV07HNL-001",
        ship_code="OV",
        year=YEAR,
        ship_name="Ovation of the Seas",
        itinerary_name="Hawaii Cruise",
    )
    db_session.add(cruise)
    db_session.commit()
    return cruise


def add_prices(db_session, cruise, prices, start=date(2027, 1, 1)):
    for offset, price in enumerate(prices):
        db_session.add(
            PriceHistory(
                cruise_id=cruise.id,
                date_scraped=start + timedelta(days=offset),
                ship_code=cruise.ship_code,
                sailing_date_range=SAILING_RANGE,
                year=YEAR,
                price=price,
            )
        )
    db_session.commit()


def request_rating(client):
    return client.get(
        "/cruise-rating",
        params={
            "package_code": "OV07HNL-001",
            "ship_code": "OV",
            "sailing_date_range": SAILING_RANGE,
            "year": YEAR,
        },
    )


def test_unknown_cruise_returns_404(client):
    response = request_rating(client)

    assert response.status_code == 404
    assert response.json() == {"detail": "Cruise not found"}


def test_cruise_with_no_history_returns_404(client, db_session):
    add_cruise(db_session)

    response = request_rating(client)

    assert response.status_code == 404
    assert response.json() == {"detail": "No price history found"}


@pytest.mark.parametrize(
    ("day_count", "days_remaining"),
    [(1, 4), (2, 3), (3, 2), (4, 1)],
)
def test_one_through_four_distinct_days_wait_for_history(
    client, db_session, day_count, days_remaining
):
    cruise = add_cruise(db_session)
    add_prices(db_session, cruise, [1200] * day_count)

    response = request_rating(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_enough_history"
    assert body["days_collected"] == day_count
    assert body["days_remaining"] == days_remaining
    expected_unit = "day" if days_remaining == 1 else "days"
    assert f"{days_remaining} {expected_unit}!" in body["message"]
    if days_remaining == 1:
        assert "1 days" not in body["message"]


def test_five_days_returns_rating_based_on_chronologically_latest_price(
    client, db_session
):
    cruise = add_cruise(db_session)
    add_prices(db_session, cruise, [1200, 1100, 1000, 900, 500])

    response = request_rating(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rated"
    assert body["current_price"] == 500.0
    assert body["average_price"] == 940.0
    assert body["discount_percent"] == 46.81
    assert body["signed_percentage"] == "+46.81%"
    assert body["label"] == "Really Great Deal"
    assert body["emoji"] == "🤩"


def test_zero_average_returns_422(client, db_session):
    cruise = add_cruise(db_session)
    add_prices(db_session, cruise, [0, 0, 0, 0, 0])

    response = request_rating(client)

    assert response.status_code == 422
    assert response.json() == {"detail": "Average price must be positive"}


def test_duplicate_rows_still_count_distinct_scrape_days(tmp_path):
    database_path = tmp_path / "duplicates.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE cruises (
                id INTEGER PRIMARY KEY,
                itinerary_name TEXT,
                length VARCHAR(50),
                ship_name TEXT,
                package_code VARCHAR(100) NOT NULL,
                ship_code VARCHAR(20) NOT NULL,
                year INTEGER NOT NULL,
                departure_port TEXT,
                ports TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY,
                date_scraped DATE NOT NULL,
                cruise_id INTEGER NOT NULL,
                ship_code VARCHAR(20) NOT NULL,
                sailing_date_range VARCHAR(100) NOT NULL,
                year INTEGER NOT NULL,
                price FLOAT NOT NULL,
                created_at DATETIME
            )
            """
        )

    duplicate_session = sessionmaker(bind=engine)()
    cruise = add_cruise(duplicate_session)
    scrape_days = [
        date(2027, 1, 1),
        date(2027, 1, 1),
        date(2027, 1, 2),
        date(2027, 1, 3),
        date(2027, 1, 4),
    ]
    for scrape_day in scrape_days:
        duplicate_session.add(
            PriceHistory(
                cruise_id=cruise.id,
                date_scraped=scrape_day,
                ship_code=cruise.ship_code,
                sailing_date_range=SAILING_RANGE,
                year=YEAR,
                price=1000,
            )
        )
    duplicate_session.commit()

    def override_get_db():
        yield duplicate_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            response = request_rating(test_client)
    finally:
        app.dependency_overrides.clear()
        duplicate_session.close()
        engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_enough_history"
    assert body["days_collected"] == 4
    assert body["days_remaining"] == 1
