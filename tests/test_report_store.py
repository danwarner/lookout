"""Tests for report storage — serialization roundtrips and file persistence."""

import json
import tempfile

from lookout.domain.entities import (
    Change,
    ChangeSeverity,
    Diff,
    ScanResult,
    Signal,
    ThreatLevel,
)
from lookout.infrastructure.file_report_store import FileReportStore


def _make_scan_result() -> ScanResult:
    """Create a realistic ScanResult for testing."""
    return ScanResult(
        timestamp="2026-02-28T10:00:00",
        radar_signals=[
            Signal(
                name="NewCo",
                website="https://newco.com",
                description="A new competitor",
                funding_status="Series A",
                founding_date="2024",
                location="SF",
                relevance_score=75,
                threat_level=ThreatLevel.HIGH,
                reasoning="Direct overlap",
                icp_overlap="Same segment",
                key_differentiators="Better UX",
            ),
            Signal(
                name="SmallCo",
                website=None,
                description="Minor player",
                relevance_score=30,
                threat_level=ThreatLevel.LOW,
            ),
        ],
        monitor_diffs=[
            Diff(
                competitor_name="RivalCo",
                changes=[
                    Change(
                        category="pricing_changes",
                        summary="Raised prices 20%",
                        previous_value="$10/mo",
                        current_value="$12/mo",
                        impact_assessment="May lose customers",
                        severity=ChangeSeverity.MEDIUM,
                        source_urls=["https://rival.com/pricing", "https://techcrunch.com/rival"],
                    ),
                    Change(
                        category="feature_changes",
                        summary="Added dark mode",
                        severity=ChangeSeverity.LOW,
                    ),
                ],
            ),
            Diff(competitor_name="OtherCo", changes=[]),
        ],
        summary="Key findings from the scan.",
    )


# --- Serialization roundtrip tests ---


def test_scan_result_roundtrip():
    """ScanResult to_dict/from_dict preserves all fields."""
    original = _make_scan_result()
    data = original.to_dict()
    restored = ScanResult.from_dict(data)

    assert restored.timestamp == original.timestamp
    assert restored.summary == original.summary
    assert len(restored.radar_signals) == 2
    assert len(restored.monitor_diffs) == 2


def test_signal_roundtrip_preserves_enums():
    """Signal enums survive serialization."""
    original = _make_scan_result()
    data = original.to_dict()
    restored = ScanResult.from_dict(data)

    sig = restored.radar_signals[0]
    assert sig.threat_level == ThreatLevel.HIGH
    assert sig.relevance_score == 75
    assert sig.name == "NewCo"
    assert sig.funding_status == "Series A"
    assert sig.website == "https://newco.com"


def test_change_roundtrip_preserves_source_urls():
    """Change source_urls survive serialization."""
    original = _make_scan_result()
    data = original.to_dict()
    restored = ScanResult.from_dict(data)

    change = restored.monitor_diffs[0].changes[0]
    assert change.severity == ChangeSeverity.MEDIUM
    assert len(change.source_urls) == 2
    assert "https://rival.com/pricing" in change.source_urls


def test_scan_result_json_serializable():
    """to_dict output is JSON-serializable."""
    sr = _make_scan_result()
    data = sr.to_dict()
    json_str = json.dumps(data)
    assert json_str  # no exception
    roundtripped = json.loads(json_str)
    assert roundtripped["timestamp"] == "2026-02-28T10:00:00"


def test_signal_none_website_roundtrip():
    """Signal with website=None survives roundtrip."""
    original = _make_scan_result()
    data = original.to_dict()
    restored = ScanResult.from_dict(data)

    sig = restored.radar_signals[1]
    assert sig.website is None
    assert sig.name == "SmallCo"


# --- FileReportStore tests ---


def test_file_report_store_save_and_load():
    """Save and load a report via FileReportStore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileReportStore(directory=tmpdir)
        sr = _make_scan_result()
        store.save(sr, "<html>test</html>", "TestCorp")

        loaded = store.load("TestCorp", "2026-02-28")
        assert loaded is not None
        assert loaded.timestamp == sr.timestamp
        assert len(loaded.radar_signals) == 2


def test_file_report_store_load_html():
    """load_html returns the saved HTML content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileReportStore(directory=tmpdir)
        sr = _make_scan_result()
        html = "<html><body>Report</body></html>"
        store.save(sr, html, "TestCorp")

        loaded_html = store.load_html("TestCorp", "2026-02-28")
        assert loaded_html == html


def test_file_report_store_list_reports():
    """list_reports returns saved reports newest first."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileReportStore(directory=tmpdir)

        sr1 = ScanResult(timestamp="2026-02-27T10:00:00", summary="older")
        sr2 = ScanResult(timestamp="2026-02-28T10:00:00", summary="newer")
        store.save(sr1, "<html>1</html>", "TestCorp")
        store.save(sr2, "<html>2</html>", "TestCorp")

        reports = store.list_reports("TestCorp")
        assert len(reports) == 2
        # Newest first
        assert "2026-02-28" in reports[0]["timestamp"]
        assert "2026-02-27" in reports[1]["timestamp"]


def test_file_report_store_load_not_found():
    """load returns None when no matching report exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileReportStore(directory=tmpdir)
        assert store.load("NonExistent", "2026-01-01") is None


def test_file_report_store_load_html_not_found():
    """load_html returns None when no matching report exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileReportStore(directory=tmpdir)
        assert store.load_html("NonExistent", "2026-01-01") is None
