"""ABC for report persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from lookout.domain.entities import ScanResult


class ReportStore(ABC):
    """Persists scan reports (JSON + HTML) for history and diffing."""

    @abstractmethod
    def save(self, scan_result: ScanResult, html: str, company_name: str,
             markdown: str = "", feature_csv: str = "") -> None:
        """Save a scan report (JSON, HTML, and optionally markdown/CSV)."""
        ...

    @abstractmethod
    def list_reports(self, company_name: str) -> list[dict]:
        """List available reports for a company, newest first.

        Returns a list of dicts with 'timestamp' and 'path' keys.
        """
        ...

    @abstractmethod
    def load(self, company_name: str, date_prefix: str) -> ScanResult | None:
        """Load a report by company name and date prefix.

        date_prefix supports fuzzy matching — e.g. "2026-02-28" matches
        the first report from that date. Returns None if not found.
        """
        ...

    @abstractmethod
    def load_html(self, company_name: str, date_prefix: str) -> str | None:
        """Load the HTML version of a report.

        Returns None if not found.
        """
        ...

    @abstractmethod
    def load_latest(self, company_name: str) -> ScanResult | None:
        """Load the most recent report. Returns None if no history."""
        ...
