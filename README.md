# Cruise Price Tracker

A browser extension and Python scraper for tracking Royal Caribbean cruise prices.

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

# Start the API
uvicorn main:app --reload

# Run the scraper manually
python scraper.py
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
- Run `scraper.py` whenever you want to perform a manual scrape.
- Local `.env` and SQLite database files are ignored by Git.
