"""Base scraper interface for modular airfare collection."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ScraperResult:
    source: str
    records: list[dict]
    status: str
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class BaseScraper(ABC):
    """
    Abstract base for airfare scrapers.

    Implementations must respect robots.txt, rate limits, and ToS.
    Do NOT bypass CAPTCHAs or bot protection.
    """

    source_name: str = "unknown"
    mode: str = "live"

    @abstractmethod
    def scrape(
        self,
        routes: list[dict],
        advance_windows: list[int],
        travel_dates: list[str] | None = None,
    ) -> ScraperResult:
        """Collect airfare observations for given routes."""
        ...

    def _make_record(
        self,
        airline: str,
        origin: str,
        destination: str,
        travel_date: str,
        advance_days: int,
        base_fare: float,
        taxes: float,
        fees: float,
        **kwargs,
    ) -> dict:
        return {
            "source": self.source_name,
            "airline": airline,
            "origin": origin,
            "destination": destination,
            "route": f"{origin}-{destination}",
            "travel_date": travel_date,
            "collection_timestamp": datetime.utcnow().isoformat(),
            "advance_purchase_days": advance_days,
            "base_fare": base_fare,
            "taxes": taxes,
            "fees": fees,
            "total_fare": base_fare + taxes + fees,
            "fare_class": kwargs.get("fare_class", "Economy"),
            "availability_status": kwargs.get("availability_status", "Available"),
            "data_mode": self.mode,
            **kwargs,
        }
