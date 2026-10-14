import csv
import os
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from backend.database import SessionLocal
from backend.date_utils import (
    build_sailing_identifier,
    format_sailing_date_range,
    normalize_sailing_date,
    parse_year,
    parse_starting_date,
)
from backend.repository import save_scraped_rows

BASE_URL = (
    "https://www.royalcaribbean.com/cruises"
    "?country=USA&currency=USD"
    "&search=visiting:EU"
    "&sort=by:RECOMMENDED"
)
CRUISE_SEARCH_URL = "https://www.royalcaribbean.com/cruises/graph"
CRUISE_SEARCH_FILTER = "visiting:EU"
CRUISE_PAGE_SIZE = 50
CSV_FILE = str(Path(__file__).resolve().parents[1] / "data" / "royal_caribbean_cruises.csv")

CRUISE_SEARCH_QUERY = """
query CruiseSearch(
  $filters: String
  $sort: CruiseSearchSort
  $pagination: CruiseSearchPagination
) {
  cruiseSearch(filters: $filters, sort: $sort, pagination: $pagination) {
    results {
      total
      cruises {
        id
        masterSailing {
          itinerary {
            name
            code
            sailingNights
            totalNights
            departurePort {
              name
            }
            ship {
              code
              name
            }
            days {
              number
              ports {
                port {
                  name
                }
              }
            }
          }
        }
        sailings {
          itinerary {
            code
            name
            sailingNights
            totalNights
            departurePort {
              name
            }
            ship {
              code
              name
            }
            days {
              number
              ports {
                port {
                  name
                }
              }
            }
          }
          startDate
          endDate
          stateroomClassPricing {
            price {
              value
            }
          }
        }
      }
    }
  }
}
"""


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip() if text else None


def safe_inner_text(locator):
    if locator.count() == 0:
        return None
    return clean_text(locator.first.inner_text())


def parse_price(text):
    if not text:
        return None

    match = re.search(r"\$\s*([\d,]+)", text)
    return f"${match.group(1)}" if match else None


def parse_available_dates(page):
    body_text = page.locator("body").inner_text()

    marker = re.search(r"\d+\s+Available dates", body_text)
    if not marker:
        return []

    dates_text = body_text[marker.end():]

    date_price_pairs = re.findall(
        r"([A-Z][a-z]{2} \d{1,2} - [A-Z][a-z]{2} \d{1,2})\s*\n\s*(\$\d[\d,]*)",
        dates_text,
    )

    return [
        {
            "sailing_date_range": date_range,
            "price": price,
        }
        for date_range, price in date_price_pairs
    ]

def parse_departure_port_from_card_text(card_text):
    match = re.search(r"ROUNDTRIP FROM:\s*(.*?)(?:CRUISE PORTS:|$)", card_text)
    return clean_text(match.group(1)) if match else None


def parse_ports_from_card_text(card_text):
    match = re.search(r"CRUISE PORTS:\s*(.*?)(?:\+ View Ports & Map|AVG PER PERSON|View \d+ dates|$)", card_text)
    return clean_text(match.group(1)) if match else None


def parse_departure_date(date_range, year):
    if not date_range or not year:
        return None

    start_date_text = date_range.split(" - ")[0]
    parsed_date = datetime.strptime(f"{start_date_text} {year}", "%b %d %Y")
    return parsed_date.date().isoformat()

def click_load_more_until_done(page):
    while True:
        load_more_button = page.locator('[data-testid="load-more-button"]')

        if load_more_button.count() == 0:
            print("No Load More button found.")
            break

        button = load_more_button.first

        if not button.is_visible() or not button.is_enabled():
            print("Load More button is hidden or disabled.")
            break

        current_card_count = page.locator('[data-testid^="cruise-card-container_"]').count()

        print(f"Clicking Load More. Current cards: {current_card_count}")

        button.scroll_into_view_if_needed()
        button.click()

        try:
            page.wait_for_function(
                """
                previousCount => {
                    return document.querySelectorAll('[data-testid^="cruise-card-container_"]').length > previousCount;
                }
                """,
                arg=current_card_count,
                timeout=20000,
            )
        except:
            print("No additional cards loaded after clicking Load More.")
            break

        page.wait_for_timeout(1000)


def fetch_cruise_page(api, skip=0, count=CRUISE_PAGE_SIZE):
    response = api.post(
        CRUISE_SEARCH_URL,
        data={
            "operationName": "CruiseSearch",
            "query": CRUISE_SEARCH_QUERY,
            "variables": {
                "filters": CRUISE_SEARCH_FILTER,
                "sort": {"by": "RECOMMENDED"},
                "pagination": {"count": count, "skip": skip},
            },
        },
    )

    if not response.ok:
        raise RuntimeError(
            f"Cruise search request failed with HTTP {response.status}: "
            f"{response.text()[:500]}"
        )

    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"Cruise search returned errors: {payload['errors']}")

    try:
        return payload["data"]["cruiseSearch"]["results"]
    except (KeyError, TypeError) as error:
        raise RuntimeError("Cruise search response is missing results") from error


def fetch_all_cruises(api):
    cruises = []
    total = None

    while total is None or len(cruises) < total:
        results = fetch_cruise_page(api, skip=len(cruises))
        page_cruises = results.get("cruises") or []
        total = results.get("total", len(cruises) + len(page_cruises))
        cruises.extend(page_cruises)

        if not page_cruises:
            break

    return cruises, total or len(cruises)


def format_api_price(sailing):
    prices = []
    for stateroom in sailing.get("stateroomClassPricing") or []:
        price = stateroom.get("price") or {}
        value = price.get("value")
        if isinstance(value, (int, float)) and value >= 0:
            prices.append(value)

    if not prices:
        return None

    lowest_price = min(prices)
    if float(lowest_price).is_integer():
        return f"${lowest_price:,.0f}"
    return f"${lowest_price:,.2f}"


def itinerary_ports(itinerary):
    departure_port = (itinerary.get("departurePort") or {}).get("name")
    ports = []

    for day in itinerary.get("days") or []:
        for visit in day.get("ports") or []:
            port_name = (visit.get("port") or {}).get("name")
            if (
                port_name
                and port_name != departure_port
                and port_name.casefold() != "cruising"
                and port_name not in ports
            ):
                ports.append(port_name)

    return ", ".join(ports) or None


def merge_non_null(base, override):
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if value is not None:
            merged[key] = value
    return merged


def cruise_rows_from_api(cruises, date_scraped):
    rows = []

    for cruise_group in cruises:
        master_itinerary = (
            (cruise_group.get("masterSailing") or {}).get("itinerary") or {}
        )

        for sailing in cruise_group.get("sailings") or []:
            sailing_itinerary = sailing.get("itinerary") or {}
            itinerary = merge_non_null(master_itinerary, sailing_itinerary)
            ship = merge_non_null(
                master_itinerary.get("ship"), sailing_itinerary.get("ship")
            )
            ship_code = ship.get("code")
            nights = itinerary.get("sailingNights") or itinerary.get("totalNights")
            length = f"{nights} Nights" if nights is not None else None
            departure_port = (itinerary.get("departurePort") or {}).get("name")
            ports = itinerary_ports(itinerary)
            package_code = sailing_itinerary.get("code")
            raw_start_date = sailing.get("startDate")
            raw_end_date = sailing.get("endDate")
            start_date = normalize_sailing_date(raw_start_date)
            end_date = normalize_sailing_date(raw_end_date)
            sailing_date_range = format_sailing_date_range(start_date, end_date)
            identifier = build_sailing_identifier(
                package_code,
                ship_code,
                sailing_date_range,
                start_date,
            )

            if not package_code or not ship_code:
                print(
                    "Skipping sailing with an incomplete identifier: "
                    f"{raw_start_date} - {raw_end_date}"
                )
                continue

            if identifier is None:
                identifier = {
                    "package_code": package_code,
                    "ship_code": ship_code,
                    "sailing_date_range": sailing_date_range,
                    "year": parse_year(start_date),
                }

            rows.append(
                {
                    "date_scraped": date_scraped,
                    "itinerary_name": itinerary.get("name"),
                    "length": length,
                    "ship_name": ship.get("name"),
                    **identifier,
                    "start_date": start_date,
                    "end_date": end_date,
                    "price": format_api_price(sailing),
                    "departure_port": departure_port,
                    "ports": ports,
                }
            )

    return rows


def run_scraper():
    with sync_playwright() as p:
        api = p.request.new_context(
            extra_http_headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            }
        )
        try:
            cruise_groups, reported_total = fetch_all_cruises(api)
        finally:
            api.dispose()

    card_count = len(cruise_groups)
    print(f"Cruise listings found: {card_count} of {reported_total}")
    all_cruises = cruise_rows_from_api(
        cruise_groups,
        datetime.now().date().isoformat(),
    )

    fieldnames = [
        "date_scraped",
        "itinerary_name",
        "length",
        "ship_name",
        "package_code",
        "ship_code",
        "year",
        "start_date",
        "end_date",
        "sailing_date_range",
        "price",
        "departure_port",
        "ports",
    ]

    file_has_content = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if not file_has_content:
            writer.writeheader()

        writer.writerows(all_cruises)

    print(f"Appended {len(all_cruises)} rows to {CSV_FILE}")

    database_summary = None
    if all_cruises:
        with SessionLocal() as session:
            database_summary = save_scraped_rows(session, all_cruises)

        print(f"Saved {len(all_cruises)} price-history rows to SQLite")
    else:
        print("No scraped rows to save to PostgreSQL")

    print("Total rows scraped:", len(all_cruises))

    missing_prices = sum(not row["price"] for row in all_cruises)
    missing_dates = sum(not row["sailing_date_range"] for row in all_cruises)
    missing_names = sum(not row["itinerary_name"] for row in all_cruises)

    print("Rows missing price:", missing_prices)
    print("Rows missing sailing date:", missing_dates)
    print("Rows missing itinerary name:", missing_names)

    return {
        "listings_found": card_count,
        "rows_scraped": len(all_cruises),
        "database": database_summary,
    }


if __name__ == "__main__":
    run_scraper()
