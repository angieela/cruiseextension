from datetime import date

from models import Cruise, PriceHistory
from price_utils import parse_price


def parse_scrape_date(value):
    if isinstance(value, date):
        return value

    return date.fromisoformat(value)


def save_scraped_rows(session, rows):
    try:
        for row in rows:
            price = parse_price(row.get("price"))
            if price is None:
                print(
                    "Warning: skipping price-history row with invalid price "
                    f"{row.get('price')!r}"
                )
                continue

            package_code = row.get("package_code")
            ship_code = row.get("ship_code")
            sailing_date_range = row.get("sailing_date_range")
            try:
                year = int(row.get("year"))
            except (TypeError, ValueError):
                year = None

            if not package_code or not ship_code or not sailing_date_range or year is None:
                print("Warning: skipping price-history row with missing identifiers")
                continue

            cruise = (
                session.query(Cruise)
                .filter_by(package_code=package_code, ship_code=ship_code, year=year)
                .one_or_none()
            )

            if cruise is None:
                cruise = Cruise(
                    package_code=package_code,
                    ship_code=ship_code,
                    year=year,
                )
                session.add(cruise)

            cruise.itinerary_name = row.get("itinerary_name")
            cruise.length = row.get("length")
            cruise.ship_name = row.get("ship_name")
            cruise.departure_port = row.get("departure_port")
            cruise.ports = row.get("ports")

            session.flush()
            scrape_date = parse_scrape_date(row["date_scraped"])
            price_history = (
                session.query(PriceHistory)
                .filter_by(
                    cruise_id=cruise.id,
                    sailing_date_range=sailing_date_range,
                    year=year,
                    date_scraped=scrape_date,
                )
                .one_or_none()
            )

            if price_history is None:
                price_history = PriceHistory(
                    cruise=cruise,
                    date_scraped=scrape_date,
                    ship_code=ship_code,
                    sailing_date_range=sailing_date_range,
                    year=year,
                    price=price,
                )
                session.add(price_history)
                action = "INSERT"
            else:
                price_history.price = price
                action = "UPDATE"

            print(
                f'DATABASE {action}: cruise_id={cruise.id}, year={year}, '
                f'sailing_date_range="{sailing_date_range}", '
                f"date_scraped={scrape_date}, price={price:g}"
            )

        session.commit()
    except Exception:
        session.rollback()
        raise
