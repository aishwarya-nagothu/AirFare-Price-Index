"""Demo mode scraper — uses synthetic data generator."""
from datetime import datetime

from backend.scrapers.base import BaseScraper, ScraperResult
from backend.services.demo_generator import generate_demo_data


class DemoScraper(BaseScraper):
    """Scraper adapter that generates synthetic demo data."""

    source_name = "DEMO_SYNTHETIC"
    mode = "demo"

    def scrape(self, routes=None, advance_windows=None, travel_dates=None) -> ScraperResult:
        started = datetime.utcnow().isoformat()
        try:
            result = generate_demo_data(days=35)
            return ScraperResult(
                source=self.source_name,
                records=[],
                status="completed",
                started_at=started,
                completed_at=datetime.utcnow().isoformat(),
            )
        except Exception as e:
            return ScraperResult(
                source=self.source_name,
                records=[],
                status="failed",
                error=str(e),
                started_at=started,
                completed_at=datetime.utcnow().isoformat(),
            )
