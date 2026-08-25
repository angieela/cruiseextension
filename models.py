from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class Cruise(Base):
    __tablename__ = "cruises"
    __table_args__ = (
        UniqueConstraint(
            "package_code",
            "ship_code",
            "year",
            name="uq_cruise_package_ship_year",
        ),
    )

    id = Column(Integer, primary_key=True)
    itinerary_name = Column(Text)
    length = Column(String(50))
    ship_name = Column(Text)
    package_code = Column(String(100), nullable=False, index=True)
    ship_code = Column(String(20), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    departure_port = Column(Text)
    ports = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    price_history = relationship(
        "PriceHistory",
        back_populates="cruise",
        cascade="all, delete-orphan",
    )


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint(
            "cruise_id",
            "sailing_date_range",
            "year",
            "date_scraped",
            name="uq_sailing_price_per_day",
        ),
    )

    id = Column(Integer, primary_key=True)
    date_scraped = Column(Date, nullable=False, index=True)
    cruise_id = Column(Integer, ForeignKey("cruises.id"), nullable=False, index=True)
    ship_code = Column(String(20), nullable=False, index=True)
    sailing_date_range = Column(String(100), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    # Changing this model does not migrate an existing database column. During
    # development, recreate the database or apply a migration if it was String.
    price = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cruise = relationship("Cruise", back_populates="price_history")
