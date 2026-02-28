"""Tests for domain entities."""

from lookout.domain.entities import (
    Change,
    ChangeSeverity,
    Competitor,
    Diff,
    ScanResult,
    Signal,
    Snapshot,
    ThreatLevel,
)
from lookout.domain.scoring import classify_threat


def test_competitor_defaults():
    c = Competitor(name="Acme", website="https://acme.com")
    assert c.track == ["pricing", "features", "jobs", "funding", "messaging"]


def test_signal_defaults():
    s = Signal(name="Acme", website=None, description="A competitor")
    assert s.relevance_score == 0
    assert s.threat_level == ThreatLevel.LOW


def test_diff_has_changes():
    d = Diff(competitor_name="Acme")
    assert not d.has_changes

    d.changes.append(Change(category="pricing_changes", summary="Price increased"))
    assert d.has_changes


def test_snapshot_creation():
    s = Snapshot(
        competitor="Acme",
        timestamp="2026-02-28T10:00:00",
        sections={"pricing": "Free tier available"},
    )
    assert s.sections["pricing"] == "Free tier available"


def test_scan_result_defaults():
    sr = ScanResult()
    assert sr.radar_signals == []
    assert sr.monitor_diffs == []
    assert sr.summary == ""
    assert sr.timestamp  # auto-generated


def test_classify_threat_high():
    assert classify_threat(85) == ThreatLevel.HIGH


def test_classify_threat_medium():
    assert classify_threat(55) == ThreatLevel.MEDIUM


def test_classify_threat_low():
    assert classify_threat(20) == ThreatLevel.LOW


def test_change_severity():
    c = Change(category="pricing_changes", summary="test", severity=ChangeSeverity.HIGH)
    assert c.severity == ChangeSeverity.HIGH


def test_change_source_urls_default():
    c = Change(category="pricing_changes", summary="test")
    assert c.source_urls == []


def test_change_source_urls():
    c = Change(
        category="pricing_changes",
        summary="test",
        source_urls=["https://example.com/pricing", "https://blog.example.com/update"],
    )
    assert len(c.source_urls) == 2
    assert "https://example.com/pricing" in c.source_urls
