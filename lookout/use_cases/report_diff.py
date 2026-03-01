"""Structural diffing between two scan reports."""

from __future__ import annotations

from dataclasses import dataclass, field

from lookout.domain.entities import ScanResult


@dataclass
class SignalChange:
    """A change in a radar signal between two reports."""

    name: str
    old_score: int | None = None
    new_score: int | None = None
    old_threat: str | None = None
    new_threat: str | None = None


@dataclass
class MonitorChange:
    """A monitor change that appeared or disappeared between reports."""

    competitor: str
    summary: str


@dataclass
class ReportDiff:
    """Structural differences between two scan reports."""

    older_timestamp: str
    newer_timestamp: str
    new_signals: list[str] = field(default_factory=list)
    removed_signals: list[str] = field(default_factory=list)
    signal_changes: list[SignalChange] = field(default_factory=list)
    new_monitor_changes: list[MonitorChange] = field(default_factory=list)
    resolved_monitor_changes: list[MonitorChange] = field(default_factory=list)
    older_summary: str = ""
    newer_summary: str = ""

    @property
    def has_differences(self) -> bool:
        return bool(
            self.new_signals
            or self.removed_signals
            or self.signal_changes
            or self.new_monitor_changes
            or self.resolved_monitor_changes
        )


def diff_reports(older: ScanResult, newer: ScanResult) -> ReportDiff:
    """Compute structural differences between two scan reports."""
    result = ReportDiff(
        older_timestamp=older.timestamp,
        newer_timestamp=newer.timestamp,
        older_summary=older.summary,
        newer_summary=newer.summary,
    )

    # Radar signal diffs
    old_signals = {s.name: s for s in older.radar_signals}
    new_signals = {s.name: s for s in newer.radar_signals}
    old_names = set(old_signals.keys())
    new_names = set(new_signals.keys())

    result.new_signals = sorted(new_names - old_names)
    result.removed_signals = sorted(old_names - new_names)

    # Check for score/threat changes in signals present in both
    for name in sorted(old_names & new_names):
        old_s = old_signals[name]
        new_s = new_signals[name]
        if old_s.relevance_score != new_s.relevance_score or old_s.threat_level != new_s.threat_level:
            result.signal_changes.append(
                SignalChange(
                    name=name,
                    old_score=old_s.relevance_score,
                    new_score=new_s.relevance_score,
                    old_threat=old_s.threat_level.value,
                    new_threat=new_s.threat_level.value,
                )
            )

    # Monitor change diffs (by competitor + summary text)
    old_changes: set[tuple[str, str]] = set()
    for diff in older.monitor_diffs:
        for change in diff.changes:
            old_changes.add((diff.competitor_name, change.summary))

    new_changes: set[tuple[str, str]] = set()
    for diff in newer.monitor_diffs:
        for change in diff.changes:
            new_changes.add((diff.competitor_name, change.summary))

    for comp, summary in sorted(new_changes - old_changes):
        result.new_monitor_changes.append(MonitorChange(competitor=comp, summary=summary))

    for comp, summary in sorted(old_changes - new_changes):
        result.resolved_monitor_changes.append(MonitorChange(competitor=comp, summary=summary))

    return result


def format_diff_for_prompt(diff: ReportDiff) -> str:
    """Convert a ReportDiff into concise plain text for LLM prompt injection.

    Returns empty string if no differences.
    """
    if not diff.has_differences:
        return ""

    lines = [f"Changes since last scan ({diff.older_timestamp}):"]

    if diff.new_signals:
        lines.append(f"- New radar signals: {', '.join(diff.new_signals)}")

    if diff.removed_signals:
        lines.append(f"- No longer detected: {', '.join(diff.removed_signals)}")

    if diff.signal_changes:
        for sc in diff.signal_changes:
            parts = []
            if sc.old_score != sc.new_score:
                parts.append(f"{sc.old_score}\u2192{sc.new_score}")
            if sc.old_threat != sc.new_threat:
                parts.append(f"{sc.old_threat}\u2192{sc.new_threat}")
            lines.append(f"- Score changes: {sc.name} {' ('.join(parts)})" if len(parts) > 1 else f"- Score changes: {sc.name} {parts[0]}")

    if diff.new_monitor_changes:
        for mc in diff.new_monitor_changes:
            lines.append(f"- New monitor changes: {mc.competitor} \u2014 {mc.summary}")

    if diff.resolved_monitor_changes:
        for mc in diff.resolved_monitor_changes:
            lines.append(f"- Resolved: {mc.competitor} \u2014 {mc.summary}")

    return "\n".join(lines)
