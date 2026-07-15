from fastapi import FastAPI
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

app = FastAPI()

# 1. Create/connect to SQLite database file
DATABASE_URL = "sqlite:///./cruises.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


# 2. Define cruises table
class Cruise(Base):
    __tablename__ = "cruises"

    id = Column(Integer, primary_key=True, index=True)
    ship = Column(String)
    destination = Column(String)
    departure_date = Column(DateTime)
    sourcesite = Column(String)
    external_id = Column(Integer, primary_key=True, index=True)
    #specifics
    room_type = "interior"

# 3. Define price_history table
class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    price = Column(Float)
    scraped_at = Column(DateTime)


# 4. Actually create the tables in cruises.db
Base.metadata.create_all(bind=engine)


# 5. Helper function to get database session
def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        pass


# 6. Home route
@app.get("/")
def home():
    return {"message": "Cruise API with database is running"}


# 7. Insert fake data route
@app.post("/seed-data")
def seed_data():
    db = get_db()

    existing_cruise = db.query(Cruise).filter(Cruise.id == 1).first()

    if existing_cruise:
        db.close()
        return {"message": "Data already exists"}

    cruise = Cruise(
        id=1,
        ship="Wonder of the Seas",
        destination="Caribbean"
    )

    db.add(cruise)

    prices = [
        PriceHistory(cruise_id=1, price=1200, scraped_at=datetime(2026, 6, 1)),
        PriceHistory(cruise_id=1, price=1150, scraped_at=datetime(2026, 6, 10)),
        PriceHistory(cruise_id=1, price=999, scraped_at=datetime(2026, 6, 22)),
    ]

    db.add_all(prices)
    db.commit()
    db.close()

    return {"message": "Fake cruise data inserted"}


# 8. Cruise score route
@app.get("/cruise-score/{cruise_id}")
def get_cruise_score(cruise_id: int):
    db = get_db()

    cruise = db.query(Cruise).filter(Cruise.id == cruise_id).first()

    if cruise is None:
        db.close()
        return {"error": "Cruise not found"}

    price_rows = (
        db.query(PriceHistory)
        .filter(PriceHistory.cruise_id == cruise_id)
        .order_by(PriceHistory.scraped_at)
        .all()
    )

    if len(price_rows) == 0:
        db.close()
        return {"error": "No price history found"}

    prices = [row.price for row in price_rows]

    current_price = prices[-1]
    average_price = sum(prices) / len(prices)

    discount_percent = ((average_price - current_price) / average_price) * 100

    if discount_percent >= 15:
        label = "Great Deal"
        score = 90
    elif discount_percent >= 5:
        label = "Okay Deal"
        score = 70
    else:
        label = "Wait"
        score = 50

    db.close()

    return {
        "cruise_id": cruise_id,
        "ship": cruise.ship,
        "destination": cruise.destination,
        "current_price": current_price,
        "average_price": round(average_price, 2),
        "discount_percent": round(discount_percent, 2),
        "score": score,
        "label": label
    }