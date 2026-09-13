from playwright.sync_api import sync_playwright
from datetime import datetime
import re
import csv
import os

from database import SessionLocal
from date_utils import build_sailing_identifier, parse_starting_date
from repository import save_scraped_rows

all_cruises = []

BASE_URL = (
    "https://www.royalcaribbean.com/cruises"
    "?country=USA&currency=USD"
    "&destinationRegionCode_EUROP=true"
    "&sort=by:RECOMMENDED"
)
CSV_FILE = "royal_caribbean_cruises.csv"


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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})

    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.locator('[data-testid^="cruise-card-container_"]').first.wait_for(timeout=60000)

    #click_load_more_until_done(page)

    cards = page.locator('[data-testid^="cruise-card-container_"]')
    card_count = cards.count()

    print("Total cards found:", card_count)

    cruise_cards = []

    for i in range(card_count):
        card = cards.nth(i)

        card_testid = card.get_attribute("data-testid")
        package_code = card_testid.replace("cruise-card-container_", "")

        length = safe_inner_text(card.locator(f'[data-testid="cruise-duration-label-{package_code}"]'))
        itinerary_name = safe_inner_text(card.locator(f'[data-testid="cruise-name-label-{package_code}"]'))
        ship_name = safe_inner_text(card.locator(f'[data-testid="cruise-ship-label-{package_code}"]'))
        card_text = card.inner_text()

        #get departure port and ports

        departure_port = safe_inner_text(card.locator(f'[data-testid="cruise-roundtrip-label-{package_code}"]'))
        ports = safe_inner_text(card.locator(f'[data-testid="cruise-ports-label-{package_code}"]'))

        if not departure_port:
            departure_port = parse_departure_port_from_card_text(card_text)

        if not ports:
            ports = parse_ports_from_card_text(card_text)

        #card_price_text = safe_inner_text(card.locator(f'[data-testid="cruise-price-label-{package_code}"]'))
        #card_price = parse_price(card_price_text)

        disclosure_text = safe_inner_text(card.locator(f'[data-testid="cruise-price-disclosure-label-{package_code}"]'))
        departure_date = parse_starting_date(disclosure_text)


        cruise_cards.append({
            "itinerary_name": itinerary_name,
            "length": length,
            "ship_name": ship_name,
            "package_code": package_code,
            "ship_code": package_code[:2],
            "departure_date": departure_date,
            #"card_price": card_price,
            "departure_port": departure_port,
            "ports": ports,
        })

    date_scraped = datetime.now().date().isoformat()

    for cruise_card in cruise_cards:
        package_code = cruise_card["package_code"]

        panel_url = f"{BASE_URL}&itineraryPanel={package_code}"
        page.goto(panel_url, wait_until="domcontentloaded")

        try:
            page.get_by_text("Available dates", exact=False).wait_for(timeout=30000)
            available_dates = parse_available_dates(page)
        except:
            print(f"No available dates found for: {cruise_card['itinerary_name']}")
            available_dates = []

        for sailing in available_dates:
            identifier = build_sailing_identifier(
                cruise_card["package_code"],
                cruise_card["ship_code"],
                sailing["sailing_date_range"],
                cruise_card["departure_date"],
            )
            if identifier is None:
                print(
                    "Skipping sailing with an incomplete identifier: "
                    f"{sailing['sailing_date_range']}"
                )
                continue

            cruise = {
                "date_scraped": date_scraped,
                "itinerary_name": cruise_card["itinerary_name"],
                "length": cruise_card["length"],
                "ship_name": cruise_card["ship_name"],
                **identifier,
                "price": sailing["price"],
                "departure_port": cruise_card["departure_port"],
                "ports": cruise_card["ports"],
            }

            all_cruises.append(cruise)

        print(f"Scraped {len(available_dates)} dates for: {cruise_card['itinerary_name']}")

    browser.close()


fieldnames = [
    "date_scraped",
    "itinerary_name",
    "length",
    "ship_name",
    "package_code",
    "ship_code",
    "year",
    "sailing_date_range",
    "price",
    "departure_port",
    "ports",
]

file_exists = os.path.exists(CSV_FILE)
file_has_content = file_exists and os.path.getsize(CSV_FILE) > 0

with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)

    if not file_has_content:
        writer.writeheader()

    writer.writerows(all_cruises)

print(f"Appended {len(all_cruises)} rows to {CSV_FILE}")

if all_cruises:
    with SessionLocal() as session:
        save_scraped_rows(session, all_cruises)

    print(f"Saved {len(all_cruises)} price-history rows to PostgreSQL")
else:
    print("No scraped rows to save to PostgreSQL")

print("Total rows scraped:", len(all_cruises))

missing_prices = [row for row in all_cruises if not row["price"]]
missing_dates = [row for row in all_cruises if not row["sailing_date_range"]]
missing_names = [row for row in all_cruises if not row["itinerary_name"]]

print("Rows missing price:", len(missing_prices))
print("Rows missing sailing date:", len(missing_dates))
print("Rows missing itinerary name:", len(missing_names))
