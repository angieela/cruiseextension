import pytest

from backend.scrape_job import (
    InvalidScrapeResultError,
    ScrapeFailure,
    run_scraper_job,
)


def valid_summary():
    return {
        "listings_found": 10,
        "rows_scraped": 25,
        "database": {"inserted": 25},
    }


def test_success_returns_summary_without_notification():
    notifications = []

    result = run_scraper_job(notifications.append, scraper=valid_summary)

    assert result == valid_summary()
    assert notifications == []


def test_scraper_exception_sends_one_structured_notification_and_reraises():
    notifications = []

    def failing_scraper():
        raise ConnectionError("Royal Caribbean request failed")

    with pytest.raises(ConnectionError, match="Royal Caribbean request failed"):
        run_scraper_job(notifications.append, scraper=failing_scraper)

    assert len(notifications) == 1
    failure = notifications[0]
    assert isinstance(failure, ScrapeFailure)
    assert failure.occurred_at
    assert failure.stage == "run_scraper"
    assert failure.error_type == "ConnectionError"
    assert failure.message == "Royal Caribbean request failed"


@pytest.mark.parametrize(
    ("summary", "message"),
    [
        ({"listings_found": 0, "rows_scraped": 0}, "invalid listing count"),
        ({"listings_found": 10, "rows_scraped": 0}, "invalid row count"),
        (None, "did not return a summary"),
    ],
)
def test_invalid_results_send_validation_notification(summary, message):
    notifications = []

    with pytest.raises(InvalidScrapeResultError, match=message):
        run_scraper_job(notifications.append, scraper=lambda: summary)

    assert len(notifications) == 1
    assert notifications[0].stage == "result_validation"
    assert notifications[0].error_type == "InvalidScrapeResultError"
    assert message in notifications[0].message


def test_notification_failure_does_not_hide_scraper_failure(capsys):
    def failing_scraper():
        raise RuntimeError("database save failed")

    def failing_notifier(_failure):
        raise OSError("email provider unavailable")

    with pytest.raises(RuntimeError, match="database save failed"):
        run_scraper_job(failing_notifier, scraper=failing_scraper)

    assert "email provider unavailable" in capsys.readouterr().err
