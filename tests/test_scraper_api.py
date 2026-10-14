import csv
from copy import deepcopy

import pytest

from backend import scraper
from backend.models import Cruise, PriceHistory
from backend.repository import save_scraped_rows
from backend.scraper import (
    CRUISE_PAGE_SIZE,
    CRUISE_SEARCH_FILTER,
    CRUISE_SEARCH_QUERY,
    CRUISE_SEARCH_URL,
    cruise_rows_from_api,
    fetch_all_cruises,
    fetch_cruise_page,
    format_api_price,
)


def make_cruise_group():
    return {
        "id": "LE07BCN-1495935368",
        "masterSailing": {
            "itinerary": {
                "name": "Western Mediterranean Cruise",
                "code": "LE07M870",
                "sailingNights": 7,
                "departurePort": {"name": "Barcelona, Spain"},
                "ship": {"code": "LE", "name": "Legend of the Seas"},
                "days": [
                    {"number": 1, "ports": [{"port": {"name": "Barcelona, Spain"}}]},
                    {"number": 2, "ports": [{"port": {"name": "Palma de Mallorca, Spain"}}]},
                    {"number": 3, "ports": [{"port": {"name": "Palma de Mallorca, Spain"}}]},
                    {"number": 4, "ports": [{"port": {"name": "Naples, Italy"}}]},
                ],
            }
        },
        "sailings": [
            {
                "itinerary": {"code": "LE07M870"},
                "startDate": "2027-09-26",
                "endDate": "2027-10-03",
                "stateroomClassPricing": [
                    {"price": {"value": 1659.92}},
                    {"price": {"value": 2100.00}},
                    {"price": None},
                ],
            }
        ],
    }


def test_format_api_price_uses_lowest_available_stateroom_price():
    sailing = make_cruise_group()["sailings"][0]

    assert format_api_price(sailing) == "$1,659.92"


def test_format_api_price_keeps_whole_dollar_prices_clean():
    sailing = {"stateroomClassPricing": [{"price": {"value": 1600.0}}]}

    assert format_api_price(sailing) == "$1,600"


def test_graphql_query_requests_itinerary_ports():
    assert CRUISE_SEARCH_QUERY.count("days {") == 2
    assert CRUISE_SEARCH_QUERY.count("ports {") == 2
    assert CRUISE_SEARCH_QUERY.count("port {") == 2


def test_format_api_price_returns_none_without_recognizable_price():
    sailing = {
        "stateroomClassPricing": [
            {"price": None},
            {"price": {"value": None}},
        ]
    }

    assert format_api_price(sailing) is None


def test_cruise_rows_from_api_builds_extension_compatible_identifiers():
    rows = cruise_rows_from_api([make_cruise_group()], "2026-09-13")

    assert rows == [
        {
            "date_scraped": "2026-09-13",
            "itinerary_name": "Western Mediterranean Cruise",
            "length": "7 Nights",
            "ship_name": "Legend of the Seas",
            "package_code": "LE07M870",
            "ship_code": "LE",
            "year": 2027,
            "sailing_date_range": "Sep 26 - Oct 3",
            "start_date": "2027-09-26",
            "end_date": "2027-10-03",
            "price": "$1,659.92",
            "departure_port": "Barcelona, Spain",
            "ports": "Palma de Mallorca, Spain, Naples, Italy",
        }
    ]


def test_cruise_rows_preserve_calendar_dates_from_timestamp_values():
    cruise_group = make_cruise_group()
    sailing = cruise_group["sailings"][0]
    sailing["startDate"] = "2027-09-26T23:30:00-10:00"
    sailing["endDate"] = "2027-10-03T00:30:00+09:00"

    [row] = cruise_rows_from_api([cruise_group], "2026-09-13")

    assert row["start_date"] == "2027-09-26"
    assert row["end_date"] == "2027-10-03"
    assert row["year"] == 2027
    assert row["sailing_date_range"] == "Sep 26 - Oct 3"


def test_cruise_rows_from_api_uses_each_sailings_itinerary_and_ports():
    cruise_group = make_cruise_group()
    second_sailing = deepcopy(cruise_group["sailings"][0])
    second_sailing.update(
        {
            "itinerary": {
                "code": "LE08M999",
                "name": "Eight Night Mediterranean Cruise",
                "sailingNights": 8,
                "departurePort": {"name": "Rome, Italy"},
                "ship": {"code": "OY", "name": "Odyssey of the Seas"},
                "days": [
                    {"number": 1, "ports": [{"port": {"name": "Rome, Italy"}}]},
                    {"number": 2, "ports": [{"port": {"name": "Cruising"}}]},
                    {"number": 3, "ports": [{"port": {"name": "Mykonos, Greece"}}]},
                    {"number": 4, "ports": [{"port": {"name": "Athens, Greece"}}]},
                ],
            },
            "startDate": "2027-10-10",
            "endDate": "2027-10-18",
        }
    )
    cruise_group["sailings"].append(second_sailing)

    rows = cruise_rows_from_api([cruise_group], "2026-09-13")

    assert rows[1]["package_code"] == "LE08M999"
    assert rows[1]["ship_code"] == "OY"
    assert rows[1]["ship_name"] == "Odyssey of the Seas"
    assert rows[1]["itinerary_name"] == "Eight Night Mediterranean Cruise"
    assert rows[1]["length"] == "8 Nights"
    assert rows[1]["departure_port"] == "Rome, Italy"
    assert rows[1]["ports"] == "Mykonos, Greece, Athens, Greece"


def test_cruise_rows_from_api_skips_sailing_with_missing_identifier():
    cruise_group = make_cruise_group()
    cruise_group["sailings"][0]["itinerary"] = None

    assert cruise_rows_from_api([cruise_group], "2026-09-13") == []


@pytest.mark.parametrize(
    "missing_field",
    ["package_code", "ship_code"],
)
def test_cruise_rows_from_api_skips_incomplete_identifiers(missing_field):
    cruise_group = make_cruise_group()
    sailing = cruise_group["sailings"][0]

    if missing_field == "package_code":
        sailing["itinerary"] = None
    else:
        cruise_group["masterSailing"]["itinerary"]["ship"]["code"] = None

    assert cruise_rows_from_api([cruise_group], "2026-09-13") == []


@pytest.mark.parametrize(
    ("start_date", "end_date", "expected_start", "expected_end"),
    [
        (None, "2027-10-03", None, "2027-10-03"),
        ("2027-09-26", None, "2027-09-26", None),
        ("bad-date", "also-bad", None, None),
    ],
)
def test_malformed_dates_do_not_discard_sailing(
    start_date,
    end_date,
    expected_start,
    expected_end,
):
    cruise_group = make_cruise_group()
    sailing = cruise_group["sailings"][0]
    sailing["startDate"] = start_date
    sailing["endDate"] = end_date

    [row] = cruise_rows_from_api([cruise_group], "2026-09-13")

    assert row["start_date"] == expected_start
    assert row["end_date"] == expected_end
    assert row["sailing_date_range"] is None
    assert row["year"] == (2027 if expected_start else None)


def test_optional_itinerary_fields_can_be_missing_without_discarding_sailing():
    cruise_group = make_cruise_group()
    itinerary = cruise_group["masterSailing"]["itinerary"]
    itinerary["name"] = None
    itinerary["sailingNights"] = None
    itinerary["totalNights"] = None
    itinerary["departurePort"] = None
    itinerary["ship"]["name"] = None
    itinerary["days"] = None

    [row] = cruise_rows_from_api([cruise_group], "2026-09-13")

    assert row["package_code"] == "LE07M870"
    assert row["ship_code"] == "LE"
    assert row["year"] == 2027
    assert row["start_date"] == "2027-09-26"
    assert row["end_date"] == "2027-10-03"
    assert row["sailing_date_range"] == "Sep 26 - Oct 3"
    assert row["itinerary_name"] is None
    assert row["length"] is None
    assert row["ship_name"] is None
    assert row["departure_port"] is None
    assert row["ports"] is None


def test_missing_price_sailing_preserves_data_and_saves_null(db_session):
    cruise_group = make_cruise_group()
    cruise_group["sailings"][0]["stateroomClassPricing"] = [
        {"price": None},
        {"price": {"value": None}},
    ]

    rows = cruise_rows_from_api([cruise_group], "2026-09-13")

    assert len(rows) == 1
    assert rows[0]["price"] is None
    assert rows[0]["package_code"] == "LE07M870"
    assert rows[0]["ship_code"] == "LE"
    assert rows[0]["itinerary_name"] == "Western Mediterranean Cruise"
    assert rows[0]["sailing_date_range"] == "Sep 26 - Oct 3"

    summary = save_scraped_rows(db_session, rows)

    assert summary == {
        "cruises_created": 1,
        "inserted": 1,
        "updated": 0,
        "skipped": 0,
    }
    cruise = db_session.query(Cruise).one()
    assert cruise.package_code == "LE07M870"
    assert cruise.start_date.isoformat() == "2027-09-26"
    assert cruise.end_date.isoformat() == "2027-10-03"
    assert cruise.date_range == "Sep 26 - Oct 3"
    assert cruise.ports == "Palma de Mallorca, Spain, Naples, Italy"
    history = db_session.query(PriceHistory).one()
    assert history.cruise_id == cruise.id
    assert history.date_scraped.isoformat() == "2026-09-13"
    assert history.price is None


class FakeApi:
    def __init__(self):
        self.skips = []
        self.requests = []

    def post(self, url, data):
        self.requests.append((url, data))
        skip = data["variables"]["pagination"]["skip"]
        self.skips.append(skip)
        cruises = [{"id": str(index)} for index in range(skip, min(skip + 50, 51))]
        return FakeResponse({"data": {"cruiseSearch": {"results": {
            "total": 51,
            "cruises": cruises,
        }}}})


class FakeResponse:
    ok = True
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_fetch_all_cruises_paginates_until_reported_total():
    api = FakeApi()

    cruises, total = fetch_all_cruises(api)

    assert len(cruises) == 51
    assert total == 51
    assert api.skips == [0, 50]
    assert [request[0] for request in api.requests] == [
        CRUISE_SEARCH_URL,
        CRUISE_SEARCH_URL,
    ]
    assert [request[1]["variables"]["pagination"] for request in api.requests] == [
        {"count": CRUISE_PAGE_SIZE, "skip": 0},
        {"count": CRUISE_PAGE_SIZE, "skip": 50},
    ]
    assert all(
        request[1]["variables"]["filters"] == CRUISE_SEARCH_FILTER
        for request in api.requests
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"errors": [{"message": "schema changed"}]}, "returned errors"),
        ({"data": {"cruiseSearch": None}}, "missing results"),
    ],
)
def test_fetch_cruise_page_rejects_incomplete_graphql_responses(payload, message):
    class ResponseApi:
        def post(self, _url, data):
            return FakeResponse(payload)

    with pytest.raises(RuntimeError, match=message):
        fetch_cruise_page(ResponseApi())


def test_duplicate_sailing_rows_resolve_to_one_database_observation(db_session):
    first_group = make_cruise_group()
    duplicate_group = deepcopy(first_group)
    duplicate_group["sailings"][0]["stateroomClassPricing"][0]["price"][
        "value"
    ] = 1499.00
    rows = cruise_rows_from_api(
        [first_group, duplicate_group],
        "2026-09-13",
    )

    summary = save_scraped_rows(db_session, rows)

    assert len(rows) == 2
    assert summary["inserted"] == 1
    assert summary["updated"] == 1
    assert db_session.query(Cruise).count() == 1
    assert db_session.query(PriceHistory).count() == 1
    assert db_session.query(PriceHistory).one().price == 1499.0


def test_distinct_parsed_sailings_receive_unique_nonempty_cruise_ids(db_session):
    cruise_group = make_cruise_group()
    second_sailing = deepcopy(cruise_group["sailings"][0])
    second_sailing["startDate"] = "2027-10-03"
    second_sailing["endDate"] = "2027-10-10"
    cruise_group["sailings"].append(second_sailing)
    rows = cruise_rows_from_api([cruise_group], "2026-09-13")

    save_scraped_rows(db_session, rows)

    cruises_by_sailing = {
        (
            cruise.package_code,
            cruise.ship_code,
            cruise.start_date.isoformat() if cruise.start_date else None,
            cruise.end_date.isoformat() if cruise.end_date else None,
        ): cruise.id
        for cruise in db_session.query(Cruise).all()
    }
    sailing_ids = {
        (
            row["package_code"],
            row["ship_code"],
            row["start_date"],
            row["end_date"],
        ): cruises_by_sailing.get(
            (
                row["package_code"],
                row["ship_code"],
                row["start_date"],
                row["end_date"],
            )
        )
        for row in rows
    }
    missing_ids = [sailing for sailing, cruise_id in sailing_ids.items() if cruise_id is None]
    sailings_by_id = {}
    for sailing, cruise_id in sailing_ids.items():
        sailings_by_id.setdefault(cruise_id, []).append(sailing)
    duplicate_ids = {
        cruise_id: sailings
        for cruise_id, sailings in sailings_by_id.items()
        if cruise_id is not None and len(sailings) > 1
    }

    assert not missing_ids, f"Sailings missing cruise_id: {missing_ids}"
    assert not duplicate_ids, f"Duplicate cruise_id values: {duplicate_ids}"
    assert len(sailing_ids) == len(rows)
    assert len(set(sailing_ids.values())) == len(rows)


class FakeApiContext:
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


class FakeRequestFactory:
    def __init__(self, api):
        self.api = api

    def new_context(self, **_kwargs):
        return self.api


class FakePlaywrightManager:
    def __init__(self, api):
        self.playwright = type(
            "FakePlaywright",
            (),
            {"request": FakeRequestFactory(api)},
        )()

    def __enter__(self):
        return self.playwright

    def __exit__(self, *_args):
        return None


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_run_scraper_writes_missing_price_csv_row_and_database_input(
    monkeypatch,
    tmp_path,
):
    cruise_group = make_cruise_group()
    cruise_group["sailings"][0]["stateroomClassPricing"] = []
    csv_path = tmp_path / "cruises.csv"
    api = FakeApiContext()
    database_rows = []

    monkeypatch.setattr(scraper, "CSV_FILE", str(csv_path))
    monkeypatch.setattr(
        scraper,
        "sync_playwright",
        lambda: FakePlaywrightManager(api),
    )
    monkeypatch.setattr(
        scraper,
        "fetch_all_cruises",
        lambda _api: ([cruise_group], 1),
    )
    monkeypatch.setattr(scraper, "SessionLocal", FakeSession)

    def capture_database_rows(_session, rows):
        database_rows.extend(rows)
        return {"cruises_created": 1, "inserted": 1, "updated": 0, "skipped": 0}

    monkeypatch.setattr(scraper, "save_scraped_rows", capture_database_rows)

    summary = scraper.run_scraper()

    with csv_path.open(newline="", encoding="utf-8") as file:
        csv_rows = list(csv.DictReader(file))

    assert summary["listings_found"] == 1
    assert summary["rows_scraped"] == 1
    assert api.disposed is True
    assert len(csv_rows) == 1
    assert csv_rows[0]["price"] == ""
    assert csv_rows[0]["package_code"] == "LE07M870"
    assert csv_rows[0]["ship_code"] == "LE"
    assert csv_rows[0]["start_date"] == "2027-09-26"
    assert csv_rows[0]["end_date"] == "2027-10-03"
    assert csv_rows[0]["sailing_date_range"] == "Sep 26 - Oct 3"
    assert csv_rows[0]["itinerary_name"] == "Western Mediterranean Cruise"
    assert csv_rows[0]["ports"] == "Palma de Mallorca, Spain, Naples, Italy"
    assert len(database_rows) == 1
    assert database_rows[0]["price"] is None
    assert database_rows[0]["package_code"] == "LE07M870"
