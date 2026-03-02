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

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "website": self.website,
            "description": self.description,
            "funding_status": self.funding_status,
            "founding_date": self.founding_date,
            "location": self.location,
            "relevance_score": self.relevance_score,
            "threat_level": self.threat_level.value,
            "reasoning": self.reasoning,
            "icp_overlap": self.icp_overlap,
            "key_differentiators": self.key_differentiators,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Signal:
        return cls(
            name=data["name"],
            website=data.get("website"),
            description=data["description"],
            funding_status=data.get("funding_status"),
            founding_date=data.get("founding_date"),
            location=data.get("location"),
            relevance_score=data.get("relevance_score", 0),
            threat_level=ThreatLevel(data.get("threat_level", "low")),
            reasoning=data.get("reasoning", ""),
            icp_overlap=data.get("icp_overlap", ""),
            key_differentiators=data.get("key_differentiators", ""),
        )


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

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "summary": self.summary,
            "previous_value": self.previous_value,
            "current_value": self.current_value,
            "impact_assessment": self.impact_assessment,
            "severity": self.severity.value,
            "source_urls": self.source_urls,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Change:
        return cls(
            category=data["category"],
            summary=data["summary"],
            previous_value=data.get("previous_value"),
            current_value=data.get("current_value"),
            impact_assessment=data.get("impact_assessment", ""),
            severity=ChangeSeverity(data.get("severity", "low")),
            source_urls=data.get("source_urls", []),
        )


@dataclass
class Diff:
    """Differences detected between two snapshots of a competitor."""

    competitor_name: str
    changes: list[Change] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0

    def to_dict(self) -> dict:
        return {
            "competitor_name": self.competitor_name,
            "changes": [c.to_dict() for c in self.changes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Diff:
        return cls(
            competitor_name=data["competitor_name"],
            changes=[Change.from_dict(c) for c in data.get("changes", [])],
        )


@dataclass
class Snapshot:
    """A point-in-time capture of a competitor's public presence."""

    competitor: str
    timestamp: str
    sections: dict[str, str | list[str]] = field(default_factory=dict)


@dataclass
class FeatureRow:
    """A single feature in the cross-competitor feature matrix."""

    feature: str
    competitors: dict[str, str]  # competitor_name → "Y" or brief note
    classification: str  # "table_stakes", "differentiating", or "unique"

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "competitors": self.competitors,
            "classification": self.classification,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FeatureRow:
        return cls(
            feature=data["feature"],
            competitors=data.get("competitors", {}),
            classification=data.get("classification", "table_stakes"),
        )


@dataclass
class FeatureMatrix:
    """Cross-competitor feature landscape matrix."""

    competitor_names: list[str] = field(default_factory=list)
    rows: list[FeatureRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "competitor_names": self.competitor_names,
            "rows": [r.to_dict() for r in self.rows],
        }

    @classmethod
    def from_dict(cls, data: dict) -> FeatureMatrix:
        return cls(
            competitor_names=data.get("competitor_names", []),
            rows=[FeatureRow.from_dict(r) for r in data.get("rows", [])],
        )


@dataclass
class ScanResult:
    """Combined results from a full scan (radar + monitor)."""

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    radar_signals: list[Signal] = field(default_factory=list)
    monitor_diffs: list[Diff] = field(default_factory=list)
    summary: str = ""
    feature_matrix: FeatureMatrix | None = None

    def to_dict(self) -> dict:
        d = {
            "timestamp": self.timestamp,
            "radar_signals": [s.to_dict() for s in self.radar_signals],
            "monitor_diffs": [d.to_dict() for d in self.monitor_diffs],
            "summary": self.summary,
        }
        if self.feature_matrix is not None:
            d["feature_matrix"] = self.feature_matrix.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ScanResult:
        fm = None
        if "feature_matrix" in data:
            fm = FeatureMatrix.from_dict(data["feature_matrix"])
        return cls(
            timestamp=data["timestamp"],
            radar_signals=[Signal.from_dict(s) for s in data.get("radar_signals", [])],
            monitor_diffs=[Diff.from_dict(d) for d in data.get("monitor_diffs", [])],
            summary=data.get("summary", ""),
            feature_matrix=fm,
        )
