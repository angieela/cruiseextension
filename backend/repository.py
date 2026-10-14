from datetime import date

from backend.date_utils import normalize_sailing_date
from backend.models import Cruise, PriceHistory
from backend.price_utils import parse_price


def parse_scrape_date(value):
    if isinstance(value, date):
        return value

    return date.fromisoformat(value)


def parse_sailing_date(value):
    normalized = normalize_sailing_date(value)
    return date.fromisoformat(normalized) if normalized else None


def save_scraped_rows(session, rows):
    summary = {
        "cruises_created": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
    }

    try:
        for row in rows:
            price = parse_price(row.get("price"))

            package_code = row.get("package_code")
            ship_code = row.get("ship_code")
            sailing_date_range = row.get("sailing_date_range")
            start_date = parse_sailing_date(row.get("start_date"))
            end_date = parse_sailing_date(row.get("end_date"))
            try:
                year = int(row.get("year"))
            except (TypeError, ValueError):
                year = None

            if not package_code or not ship_code:
                print("Warning: skipping price-history row with missing identifiers")
                summary["skipped"] += 1
                continue

            cruise = (
                session.query(Cruise)
                .filter_by(
                    package_code=package_code,
                    ship_code=ship_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                .one_or_none()
            )

            if cruise is None:
                cruise = Cruise(
                    package_code=package_code,
                    ship_code=ship_code,
                    year=year,
                    start_date=start_date,
                    end_date=end_date,
                )
                session.add(cruise)
                summary["cruises_created"] += 1

            cruise.itinerary_name = row.get("itinerary_name")
            cruise.length = row.get("length")
            cruise.ship_name = row.get("ship_name")
            cruise.year = year
            cruise.date_range = sailing_date_range
            cruise.departure_port = row.get("departure_port")
            cruise.ports = row.get("ports")

            session.flush()
            scrape_date = parse_scrape_date(row["date_scraped"])
            price_history = (
                session.query(PriceHistory)
                .filter_by(
                    cruise_id=cruise.id,
                    date_scraped=scrape_date,
                )
                .one_or_none()
            )

            if price_history is None:
                price_history = PriceHistory(
                    cruise=cruise,
                    date_scraped=scrape_date,
                    price=price,
                )
                session.add(price_history)
                summary["inserted"] += 1
            else:
                price_history.price = price
                summary["updated"] += 1

        session.commit()
        return summary
    except Exception:
        session.rollback()
        raise
