from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Base, Cruise, PriceHistory


app = FastAPI(title="Cruise Price Tracker API")

MINIMUM_SCRAPE_DAYS = 5


def get_price_rating(discount_percent: float):
    """Return the MVP label and emoji for a percent below/above average."""
    if discount_percent >= 30:
        return "Really Great Deal", "🤩"
    if discount_percent >= 20:
        return "Great Deal", "🔥"
    if discount_percent >= 5:
        return "Good Deal", "👍"
    if discount_percent >= -5:
        return "Okay", "😐"
    if discount_percent >= -20:
        return "Not the Best", "👎"
    if discount_percent >= -30:
        return "Expensive", "💸"
    return "Really Expensive", "🚨"

# Both the API and scraper use the models and engine shared above.
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def home():
    return {
        "message": "Cruise API with shared database is running",
        "database": engine.dialect.name,
    }


@app.post("/seed-data")
def seed_data(db: Session = Depends(get_db)):
    cruise = (
        db.query(Cruise)
        .filter_by(package_code="DEMO-WN-001", ship_code="WN", year=2027)
        .one_or_none()
    )

    if cruise is None:
        cruise = Cruise(
            package_code="DEMO-WN-001",
            ship_code="WN",
            year=2027,
        )
        db.add(cruise)

    cruise.ship_name = "Wonder of the Seas"
    cruise.itinerary_name = "Demo Caribbean Cruise"
    cruise.length = "7 nights"
    cruise.departure_port = "Miami, Florida"
    cruise.ports = "Nassau, Perfect Day at CocoCay"
    db.flush()

    sailing_date_range = "Jan 30 - Feb 6, 2027"
    seeded_prices = [
        (date(2026, 6, 1), 1200.0),
        (date(2026, 6, 10), 1150.0),
        (date(2026, 6, 22), 999.0),
        (date(2026, 6, 23), 1100.0),
        (date(2026, 6, 24), 900.0),
    ]

    for scrape_date, price in seeded_prices:
        price_history = (
            db.query(PriceHistory)
            .filter_by(
                cruise_id=cruise.id,
                sailing_date_range=sailing_date_range,
                year=cruise.year,
                date_scraped=scrape_date,
            )
            .one_or_none()
        )
        if price_history is None:
            price_history = PriceHistory(
                cruise_id=cruise.id,
                ship_code=cruise.ship_code,
                sailing_date_range=sailing_date_range,
                year=cruise.year,
                date_scraped=scrape_date,
                price=price,
            )
            db.add(price_history)
        else:
            price_history.price = price

    db.commit()

    return {
        "message": "Demo cruise data seeded",
        "cruise_id": cruise.id,
        "sailing_date_range": sailing_date_range,
        "year": cruise.year,
        "scrape_days": len(seeded_prices),
    }


@app.get("/cruise-score/{cruise_id}")
def get_cruise_score(
    cruise_id: int,
    sailing_date_range: str,
    year: int,
    db: Session = Depends(get_db),
):
    cruise = db.query(Cruise).filter(Cruise.id == cruise_id).one_or_none()
    if cruise is None:
        raise HTTPException(status_code=404, detail="Cruise not found")

    price_rows = (
        db.query(PriceHistory)
        .filter(
            PriceHistory.cruise_id == cruise.id,
            PriceHistory.sailing_date_range == sailing_date_range,
            PriceHistory.year == year,
        )
        .order_by(PriceHistory.date_scraped)
        .all()
    )
    if not price_rows:
        raise HTTPException(status_code=404, detail="No price history found")

    distinct_scrape_days = {row.date_scraped for row in price_rows}
    latest_price_row = max(price_rows, key=lambda row: row.date_scraped)
    if len(distinct_scrape_days) < MINIMUM_SCRAPE_DAYS:
        days_remaining = MINIMUM_SCRAPE_DAYS - len(distinct_scrape_days)
        day_word = "day" if days_remaining == 1 else "days"
        return {
            "status": "not_enough_history",
            "cruise_id": cruise_id,
            "year": year,
            "sailing_date_range": sailing_date_range,
            "current_price": latest_price_row.price,
            "days_collected": len(distinct_scrape_days),
            "days_remaining": days_remaining,
            "message": (
                "Posting is too recent, "
                f"come again in {days_remaining} {day_word}!"
            ),
        }

    prices = [row.price for row in price_rows]
    current_price = latest_price_row.price
    average_price = sum(prices) / len(prices)
    if average_price <= 0:
        raise HTTPException(status_code=422, detail="Average price must be positive")

    discount_percent = ((average_price - current_price) / average_price) * 100
    label, emoji = get_price_rating(discount_percent)

    return {
        "status": "rated",
        "cruise_id": cruise_id,
        "year": year,
        "sailing_date_range": sailing_date_range,
        "ship": cruise.ship_name,
        "destination": cruise.itinerary_name,
        "current_price": current_price,
        "average_price": round(average_price, 2),
        "discount_percent": round(discount_percent, 2),
        "signed_percentage": f"{discount_percent:+.2f}%",
        "label": label,
        "emoji": emoji,
    }
