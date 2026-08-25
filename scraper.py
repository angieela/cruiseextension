from playwright.sync_api import sync_playwright
from datetime import datetime
import re
import csv
import os

from database import SessionLocal
from price_utils import parse_price
from repository import save_scraped_rows

all_cruises = []

BASE_URL = "https://www.royalcaribbean.com/cruises?country=USA&currency=USD&ecid=ps_mdt_lfbrnd_goo_12397&gad_campaignid=10439537189&gad_source=1&gbraid=0AAAAADhYZLSyXY8IO7LBLRlV8Elp_Ct73&gclid=Cj0KCQjw39zSBhDhARIsANammDviOcDtqMCypfKfH2ZiYdIJFfAzIyOLuH7F2odzxKBsgwSpNV0KJHoaAu3mEALw_wcB&gclsrc=aw.ds&hp_search_widget=home&search=departurePort:BYE,FLL,GAL,LAX,MIA,PCN,SAN,SEA,TPA&sort=by:RECOMMENDED"
CSV_FILE = "royal_caribbean_cruises.csv"
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
SAILING_DATE_PATTERN = re.compile(
    r"([A-Z][a-z]{2} \d{1,2} - [A-Z][a-z]{2} \d{1,2}(?:,? \d{4})?)"
)


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip() if text else None


def safe_inner_text(locator):
    if locator.count() == 0:
        return None
    return clean_text(locator.first.inner_text())


def parse_year(*values):
    for value in values:
        if value is None:
            continue

        match = YEAR_PATTERN.search(str(value))
        if match:
            return int(match.group(1))

    return None


def parse_starting_date(text):
    if not text:
        return None

    match = re.search(r"valid for ([A-Za-z]{3} \d{1,2}, \d{4})", text)
    return match.group(1) if match else None


def parse_available_dates(page, departure_date=None):
    sailing_section = page.locator('[data-testid="sailing-dates-section"]')
    if sailing_section.count() == 0:
        return []

    sailing_groups = sailing_section.first.evaluate(
        """
        section => {
            const groupedItems = new Set();
            const grouped = [];

            section.querySelectorAll('[data-testid^="year-label-"]').forEach(label => {
                const yearGroup = label.parentElement;
                if (!yearGroup) return;

                yearGroup.querySelectorAll('[data-testid="sailing-date-item"]').forEach(item => {
                    groupedItems.add(item);
                    grouped.push({
                        yearText: label.textContent || "",
                        itemText: item.innerText || item.textContent || "",
                    });
                });
            });

            const ungrouped = Array.from(
                section.querySelectorAll('[data-testid="sailing-date-item"]')
            )
                .filter(item => !groupedItems.has(item))
                .map(item => ({
                    yearText: "",
                    itemText: item.innerText || item.textContent || "",
                }));

            return [...grouped, ...ungrouped];
        }
        """
    )

    available_dates = []
    for sailing in sailing_groups:
        item_text = clean_text(sailing.get("itemText"))
        date_match = SAILING_DATE_PATTERN.search(item_text or "")
        date_range = date_match.group(1) if date_match else None
        price = parse_price(item_text)

        if not date_range:
            print(f"Warning: skipping invalid sailing date item {item_text!r}")
            continue
        if price is None:
            print(f"Warning: skipping invalid price in {item_text!r} for {date_range}")
            continue

        year = parse_year(sailing.get("yearText"), date_range, departure_date)
        if year is None:
            print(f"Warning: skipping sailing with no year: {date_range}")
            continue

        print(
            f'SCRAPED: year={year}, sailing_date_range="{date_range}", '
            f"price={price:g}"
        )
        available_dates.append({
            "sailing_date_range": date_range,
            "year": year,
            "price": price,
        })

    return available_dates

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

    for cruise_card in cruise_cards[:3]:
        package_code = cruise_card["package_code"]

        panel_url = f"{BASE_URL}&itineraryPanel={package_code}"
        page.goto(panel_url, wait_until="domcontentloaded")

        try:
            page.get_by_text("Available dates", exact=False).wait_for(timeout=30000)
            available_dates = parse_available_dates(
                page,
                departure_date=cruise_card["departure_date"],
            )
        except:
            print(f"No available dates found for: {cruise_card['itinerary_name']}")
            available_dates = []

        for sailing in available_dates:
            cruise = {
                "date_scraped": date_scraped,
                "itinerary_name": cruise_card["itinerary_name"],
                "length": cruise_card["length"],
                "ship_name": cruise_card["ship_name"],
                "package_code": cruise_card["package_code"],
                "ship_code": cruise_card["ship_code"],
                "year": sailing["year"],
                #"card_price": cruise_card["card_price"],
                "sailing_date_range": sailing["sailing_date_range"],
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
    #"card_price",
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
