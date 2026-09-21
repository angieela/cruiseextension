from dataclasses import dataclass
from datetime import datetime
import sys
from typing import Callable

from scraper import run_scraper


@dataclass(frozen=True)
class ScrapeFailure:
    occurred_at: str
    stage: str
    error_type: str
    message: str


class InvalidScrapeResultError(RuntimeError):
    pass


FailureNotifier = Callable[[ScrapeFailure], None]


def validate_scrape_summary(summary):
    if not isinstance(summary, dict):
        raise InvalidScrapeResultError("Scraper did not return a summary")

    listings_found = summary.get("listings_found")
    rows_scraped = summary.get("rows_scraped")
    if not isinstance(listings_found, int) or listings_found <= 0:
        raise InvalidScrapeResultError(
            f"Scraper returned an invalid listing count: {listings_found!r}"
        )
    if not isinstance(rows_scraped, int) or rows_scraped <= 0:
        raise InvalidScrapeResultError(
            f"Scraper returned an invalid row count: {rows_scraped!r}"
        )


def run_scraper_job(
    notify_failure: FailureNotifier,
    scraper: Callable[[], dict] = run_scraper,
):
    """Run one scrape and notify once if it raises or returns invalid counts.

    A future scheduler should call this function and provide an email-backed
    ``notify_failure`` callback. This function does not schedule work or select
    an email provider.
    """
    stage = "run_scraper"
    try:
        summary = scraper()
        stage = "result_validation"
        validate_scrape_summary(summary)
        return summary
    except Exception as error:
        failure = ScrapeFailure(
            occurred_at=datetime.now().astimezone().isoformat(),
            stage=stage,
            error_type=type(error).__name__,
            message=str(error),
        )
        try:
            notify_failure(failure)
        except Exception as notification_error:
            print(
                "Failure notification could not be sent: "
                f"{type(notification_error).__name__}: {notification_error}",
                file=sys.stderr,
            )
        raise
