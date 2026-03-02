"""Tests for domain entities."""

from lookout.domain.entities import (
    Change,
    ChangeSeverity,
    Competitor,
    Diff,
    FeatureMatrix,
    FeatureRow,
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


def test_feature_row_creation_and_roundtrip():
    row = FeatureRow(
        feature="Desk Booking",
        competitors={"Acme": "Y", "Globex": "Calendar-based"},
        classification="differentiating",
    )
    d = row.to_dict()
    assert d["feature"] == "Desk Booking"
    assert d["competitors"]["Acme"] == "Y"
    assert d["classification"] == "differentiating"

    restored = FeatureRow.from_dict(d)
    assert restored.feature == row.feature
    assert restored.competitors == row.competitors
    assert restored.classification == row.classification


def test_feature_matrix_roundtrip():
    matrix = FeatureMatrix(
        competitor_names=["Acme", "Globex"],
        rows=[
            FeatureRow(feature="SSO", competitors={"Acme": "Y", "Globex": "Y"}, classification="table_stakes"),
            FeatureRow(feature="AI Reports", competitors={"Acme": "Y"}, classification="unique"),
        ],
    )
    d = matrix.to_dict()
    assert d["competitor_names"] == ["Acme", "Globex"]
    assert len(d["rows"]) == 2

    restored = FeatureMatrix.from_dict(d)
    assert restored.competitor_names == matrix.competitor_names
    assert len(restored.rows) == 2
    assert restored.rows[0].feature == "SSO"
    assert restored.rows[1].classification == "unique"


def test_scan_result_with_feature_matrix_roundtrip():
    matrix = FeatureMatrix(
        competitor_names=["Acme"],
        rows=[FeatureRow(feature="API", competitors={"Acme": "Y"}, classification="table_stakes")],
    )
    sr = ScanResult(
        timestamp="2026-03-01T00:00:00",
        summary="Test summary",
        feature_matrix=matrix,
    )
    d = sr.to_dict()
    assert "feature_matrix" in d
    assert d["feature_matrix"]["competitor_names"] == ["Acme"]

    restored = ScanResult.from_dict(d)
    assert restored.feature_matrix is not None
    assert restored.feature_matrix.rows[0].feature == "API"


def test_scan_result_backward_compat_no_feature_matrix():
    """Old report dicts without feature_matrix should deserialize cleanly."""
    d = {
        "timestamp": "2026-02-28T00:00:00",
        "radar_signals": [],
        "monitor_diffs": [],
        "summary": "Old report",
    }
    sr = ScanResult.from_dict(d)
    assert sr.feature_matrix is None
    assert sr.summary == "Old report"
