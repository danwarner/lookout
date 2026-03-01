"""Tests for structural report diffing."""

from lookout.domain.entities import (
    Change,
    ChangeSeverity,
    Diff,
    ScanResult,
    Signal,
    ThreatLevel,
)
from lookout.use_cases.report_diff import diff_reports


def test_new_radar_signal_detected():
    """A signal in newer but not older is reported as new."""
    older = ScanResult(
        timestamp="2026-02-27T10:00:00",
        radar_signals=[
            Signal(name="ExistingCo", website=None, description="Old competitor", relevance_score=50),
        ],
    )
    newer = ScanResult(
        timestamp="2026-02-28T10:00:00",
        radar_signals=[
            Signal(name="ExistingCo", website=None, description="Old competitor", relevance_score=50),
            Signal(name="NewCo", website="https://newco.com", description="New competitor", relevance_score=70),
        ],
    )

    rd = diff_reports(older, newer)
    assert rd.has_differences
    assert "NewCo" in rd.new_signals
    assert "ExistingCo" not in rd.new_signals


def test_removed_radar_signal_detected():
    """A signal in older but not newer is reported as removed."""
    older = ScanResult(
        timestamp="2026-02-27T10:00:00",
        radar_signals=[
            Signal(name="GoneCo", website=None, description="Was here", relevance_score=40),
            Signal(name="StillCo", website=None, description="Still here", relevance_score=60),
        ],
    )
    newer = ScanResult(
        timestamp="2026-02-28T10:00:00",
        radar_signals=[
            Signal(name="StillCo", website=None, description="Still here", relevance_score=60),
        ],
    )

    rd = diff_reports(older, newer)
    assert rd.has_differences
    assert "GoneCo" in rd.removed_signals
    assert "StillCo" not in rd.removed_signals


def test_score_and_threat_changes_detected():
    """Score or threat level changes for the same signal are detected."""
    older = ScanResult(
        timestamp="2026-02-27T10:00:00",
        radar_signals=[
            Signal(name="RisingCo", website=None, description="Rising", relevance_score=40, threat_level=ThreatLevel.LOW),
        ],
    )
    newer = ScanResult(
        timestamp="2026-02-28T10:00:00",
        radar_signals=[
            Signal(name="RisingCo", website=None, description="Rising", relevance_score=75, threat_level=ThreatLevel.HIGH),
        ],
    )

    rd = diff_reports(older, newer)
    assert rd.has_differences
    assert len(rd.signal_changes) == 1
    sc = rd.signal_changes[0]
    assert sc.name == "RisingCo"
    assert sc.old_score == 40
    assert sc.new_score == 75
    assert sc.old_threat == "low"
    assert sc.new_threat == "high"


def test_no_changes_between_identical_reports():
    """Identical reports produce no differences."""
    signals = [
        Signal(name="SameCo", website=None, description="Same", relevance_score=50, threat_level=ThreatLevel.MEDIUM),
    ]
    diffs = [
        Diff(
            competitor_name="Rival",
            changes=[Change(category="pricing", summary="Same change", severity=ChangeSeverity.LOW)],
        ),
    ]
    older = ScanResult(timestamp="2026-02-27T10:00:00", radar_signals=signals, monitor_diffs=diffs, summary="Same")
    newer = ScanResult(timestamp="2026-02-28T10:00:00", radar_signals=signals, monitor_diffs=diffs, summary="Same")

    rd = diff_reports(older, newer)
    assert not rd.has_differences


def test_new_monitor_change_detected():
    """A monitor change in newer but not older is reported."""
    older = ScanResult(timestamp="2026-02-27T10:00:00", monitor_diffs=[])
    newer = ScanResult(
        timestamp="2026-02-28T10:00:00",
        monitor_diffs=[
            Diff(
                competitor_name="RivalCo",
                changes=[Change(category="pricing", summary="Raised prices", severity=ChangeSeverity.HIGH)],
            ),
        ],
    )

    rd = diff_reports(older, newer)
    assert rd.has_differences
    assert len(rd.new_monitor_changes) == 1
    assert rd.new_monitor_changes[0].competitor == "RivalCo"
    assert rd.new_monitor_changes[0].summary == "Raised prices"


def test_resolved_monitor_change_detected():
    """A monitor change in older but not newer is reported as resolved."""
    older = ScanResult(
        timestamp="2026-02-27T10:00:00",
        monitor_diffs=[
            Diff(
                competitor_name="RivalCo",
                changes=[Change(category="pricing", summary="Old issue", severity=ChangeSeverity.LOW)],
            ),
        ],
    )
    newer = ScanResult(timestamp="2026-02-28T10:00:00", monitor_diffs=[])

    rd = diff_reports(older, newer)
    assert rd.has_differences
    assert len(rd.resolved_monitor_changes) == 1
    assert rd.resolved_monitor_changes[0].summary == "Old issue"
