"""Domain entities for Lookout."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ThreatLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChangeSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Competitor:
    """A known competitor being tracked."""

    name: str
    website: str
    track: list[str] = field(default_factory=lambda: ["pricing", "features", "jobs", "funding", "messaging"])


@dataclass
class Signal:
    """A discovered company from a radar scan."""

    name: str
    website: str | None
    description: str
    funding_status: str | None = None
    founding_date: str | None = None
    location: str | None = None
    relevance_score: int = 0
    threat_level: ThreatLevel = ThreatLevel.LOW
    reasoning: str = ""
    icp_overlap: str = ""
    key_differentiators: str = ""


@dataclass
class Change:
    """A detected change for a monitored competitor."""

    category: str
    summary: str
    previous_value: str | None = None
    current_value: str | None = None
    impact_assessment: str = ""
    severity: ChangeSeverity = ChangeSeverity.LOW
    source_urls: list[str] = field(default_factory=list)


@dataclass
class Diff:
    """Differences detected between two snapshots of a competitor."""

    competitor_name: str
    changes: list[Change] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0


@dataclass
class Snapshot:
    """A point-in-time capture of a competitor's public presence."""

    competitor: str
    timestamp: str
    sections: dict[str, str | list[str]] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Combined results from a full scan (radar + monitor)."""

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    radar_signals: list[Signal] = field(default_factory=list)
    monitor_diffs: list[Diff] = field(default_factory=list)
    summary: str = ""
