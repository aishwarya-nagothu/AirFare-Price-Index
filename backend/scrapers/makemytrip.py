"""
MakeMyTrip scraper adapter (LIVE mode placeholder).

IMPORTANT:
- This is an architectural demonstration only.
- MakeMyTrip employs bot protection, CAPTCHAs, and dynamic rendering.
- This scraper does NOT bypass security controls.
- Use DEMO mode for reliable demonstrations.

To enable live scraping in production:
1. Obtain official API access or data partnership
2. Respect robots.txt at https://www.makemytrip.com/robots.txt
3. Implement rate limiting (max 1 req/sec)
4. Use Playwright with ethical scraping practices
"""
import logging
from datetime import datetime

from backend.scrapers.base import BaseScraper, ScraperResult

logger = logging.getLogger(__name__)


class MakeMyTripScraper(BaseScraper):
    """
    Placeholder for MakeMyTrip OTA scraper.

    Architecture demonstrates how live sources would be integrated.
    Returns empty results with documented status when live scraping
    is not permitted or feasible.
    """

    source_name = "MakeMyTrip"
    mode = "live"
    BASE_URL = "https://www.makemytrip.com/flights/"

    def scrape(self, routes=None, advance_windows=None, travel_dates=None) -> ScraperResult:
        started = datetime.utcnow().isoformat()
        logger.info(
            "MakeMyTrip live scraper invoked — returning empty (bot protection active). "
            "Use DATA_MODE=demo for demonstration."
        )
        return ScraperResult(
            source=self.source_name,
            records=[],
            status="skipped",
            error=(
                "Live scraping not enabled. MakeMyTrip employs bot protection. "
                "Use DATA_MODE=demo or obtain official API access."
            ),
            started_at=started,
            completed_at=datetime.utcnow().isoformat(),
        )

    def _build_search_url(self, origin: str, destination: str, date: str) -> str:
        """Build search URL for documentation purposes."""
        return f"{self.BASE_URL}?from={origin}&to={destination}&date={date}"
