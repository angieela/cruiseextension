# Europe Cruise Price Tracker

A Chrome extension, Playwright scraper, and FastAPI/SQLAlchemy backend for tracking
Royal Caribbean Europe cruise prices over time.

## What it does

- Loads Royal Caribbean's `/cruises` results with the
  `destinationRegionCode_EUROP=true` Europe
  filter supplied in `scraper.py`.
- Repeatedly loads more results until every currently available card is rendered.
- Extracts each itinerary and its sailing dates using stable `data-testid` and
  `data-*` attributes.
- Stores one numeric price-history record per package code, ship code, sailing
  date range, year, and scrape day.
- Shows a rating badge on Royal Caribbean result cards after at least five daily
  observations exist for that exact sailing.

## Setup

These commands are for macOS and Linux.

```bash
# Create and activate the virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python and browser dependencies
python -m pip install -r requirements.txt
playwright install chromium

# Create the database tables
python init_db.py

# Start the API used by the extension
uvicorn main:app --reload

# In another terminal, run the Europe scraper
python scraper.py
```

The scraper uses the installed Google Chrome channel in visible mode by default.
Royal Caribbean currently serves an error page to automated headless Chromium,
so visible Chrome is the reliable local mode:

```bash
python scraper.py
```

The browser settings remain configurable for other environments:

```bash
SCRAPER_BROWSER_CHANNEL=chrome SCRAPER_HEADLESS=false python scraper.py
```

By default, the API and scraper share a local SQLite database at `cruises.db`.
No database configuration is required for this local setup.

To use PostgreSQL instead, create `.env` and set `DATABASE_URL`:

```bash
cp .env.example .env
```

Then replace its SQLite URL with the PostgreSQL example shown in that file. Both
the API and scraper read the same setting from `database.py`.

## Command notes

- Creating and activating `.venv` is normally required only once per local setup. Activate it again when starting a new terminal session.
- `playwright install chromium` is normally required only once.
- `init_db.py` creates missing database tables. It does not migrate existing tables when a model's column type changes.
- `uvicorn main:app --reload` starts the FastAPI development server.
- `python scraper.py` loads all current Europe listings, appends a CSV snapshot,
  and inserts or updates the shared database.
- Local `.env` and SQLite database files are ignored by Git.

## Load the Chrome extension

1. Start the API at `http://127.0.0.1:8000`.
2. Open `chrome://extensions`, enable **Developer mode**, and choose
   **Load unpacked**.
3. Select this project folder.
4. Visit Royal Caribbean's Europe-filtered cruise results.

The local API returns a waiting message until a sailing has five distinct scrape
days. After that, the badge shows an emoji, signed percentage from average, and
the seven-band price rating.

Daily scheduling is deployment-specific. During local development, run the
scraper once per day with cron, launchd, or another scheduler.

## Run the tests

Install the development dependencies and run pytest:

```bash
python -m pip install -r requirements-dev.txt
pytest -v
```

The tests force application imports to use an in-memory database and create a
separate temporary SQLite database per test, so they never read or write the
local `cruises.db` file.
