"""JSON/HTML file-based report persistence."""

from __future__ import annotations

import json
from pathlib import Path

from lookout.domain.entities import ScanResult
from lookout.interfaces.report_store import ReportStore


def _sanitize_name(name: str) -> str:
    """Convert a company name to a safe filename."""
    return name.lower().replace(" ", "_").replace("/", "_")


class FileReportStore(ReportStore):
    """Persists reports as JSON + HTML files in a directory."""

    def __init__(self, directory: str | Path = "reports"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, scan_result: ScanResult, html: str, company_name: str) -> None:
        safe_name = _sanitize_name(company_name)
        ts = scan_result.timestamp.replace(":", "-").replace(".", "-")
        data = scan_result.to_dict()

        # Save timestamped JSON
        json_path = self.directory / f"{safe_name}_{ts}.json"
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        # Save timestamped HTML
        html_path = self.directory / f"{safe_name}_{ts}.html"
        with open(html_path, "w") as f:
            f.write(html)

        # Save latest JSON (overwriting previous)
        latest_path = self.directory / f"{safe_name}_latest.json"
        with open(latest_path, "w") as f:
            json.dump(data, f, indent=2)

    def list_reports(self, company_name: str) -> list[dict]:
        safe_name = _sanitize_name(company_name)
        reports = []
        for path in self.directory.glob(f"{safe_name}_*.json"):
            if path.stem.endswith("_latest"):
                continue
            # Extract timestamp from filename: {safe_name}_{timestamp}.json
            ts_part = path.stem[len(safe_name) + 1 :]
            reports.append({"timestamp": ts_part, "path": str(path)})
        # Sort newest first
        reports.sort(key=lambda r: r["timestamp"], reverse=True)
        return reports

    def load(self, company_name: str, date_prefix: str) -> ScanResult | None:
        path = self._find_report(company_name, date_prefix, ".json")
        if path is None:
            return None
        with open(path) as f:
            data = json.load(f)
        return ScanResult.from_dict(data)

    def load_html(self, company_name: str, date_prefix: str) -> str | None:
        path = self._find_report(company_name, date_prefix, ".html")
        if path is None:
            return None
        with open(path) as f:
            return f.read()

    def load_latest(self, company_name: str) -> ScanResult | None:
        safe_name = _sanitize_name(company_name)
        latest_path = self.directory / f"{safe_name}_latest.json"
        if not latest_path.exists():
            return None
        with open(latest_path) as f:
            data = json.load(f)
        return ScanResult.from_dict(data)

    def _find_report(self, company_name: str, date_prefix: str, ext: str) -> Path | None:
        """Find a report file matching a date prefix."""
        safe_name = _sanitize_name(company_name)
        # Normalize prefix: allow "2026-02-28" to match "2026-02-28T10-00-00"
        normalized = date_prefix.replace(":", "-").replace(".", "-")
        for path in sorted(self.directory.glob(f"{safe_name}_*{ext}"), reverse=True):
            if path.stem.endswith("_latest"):
                continue
            ts_part = path.stem[len(safe_name) + 1 :]
            if ts_part.startswith(normalized):
                return path
        return None
