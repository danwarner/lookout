"""ABC for web search capability."""

from abc import ABC, abstractmethod


class SearchProvider(ABC):
    """Provides web search for discovery (radar) and intel gathering (monitor)."""

    @abstractmethod
    def search_market(self, keywords: list[str], market_definition: str, max_searches: int = 10) -> list[dict]:
        """Search for companies in a market.

        Used by radar scan to discover unknown competitors.
        Returns a list of raw company info dicts found via search.
        """
        ...

    @abstractmethod
    def gather_competitor_intel(
        self, competitor_name: str, website: str, track_sections: list[str], max_searches: int = 5
    ) -> dict[str, str | list[str]]:
        """Gather current intelligence on a known competitor.

        Used by monitor scan to get current state for diffing.
        Returns a dict of sections (pricing, features, jobs, etc.).
        """
        ...
