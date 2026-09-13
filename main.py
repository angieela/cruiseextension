from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Base, Cruise, PriceHistory


app = FastAPI(title="Cruise Price Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.royalcaribbean.com",
        "https://royalcaribbean.com",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

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


def build_cruise_score(cruise, sailing_date_range, year, db):
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
            "cruise_id": cruise.id,
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
        "cruise_id": cruise.id,
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


@app.get("/")
def home():
    return {
        "message": "Cruise API with shared database is running",
        "database": engine.dialect.name,
    }


@app.get("/cruise-rating")
def get_cruise_rating_by_identifiers(
    package_code: str,
    ship_code: str,
    sailing_date_range: str,
    year: int,
    db: Session = Depends(get_db),
):
    cruise = (
        db.query(Cruise)
        .filter_by(package_code=package_code, ship_code=ship_code, year=year)
        .one_or_none()
    )
    if cruise is None:
        raise HTTPException(status_code=404, detail="Cruise not found")

    return build_cruise_score(cruise, sailing_date_range, year, db)


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

    return build_cruise_score(cruise, sailing_date_range, year, db)
