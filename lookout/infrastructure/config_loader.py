"""YAML config parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from lookout.domain.entities import Competitor


@dataclass
class CompanyConfig:
    name: str
    description: str
    website: str
    competitive_wedge: str = ""


@dataclass
class MarketConfig:
    definition: str
    primary_keywords: list[str]
    negative_keywords: list[str] = field(default_factory=list)
    icp_overlap_signals: list[str] = field(default_factory=list)


@dataclass
class EmailConfig:
    to: str
    from_addr: str
    subject_prefix: str = "[Lookout]"


@dataclass
class RadarConfig:
    max_searches: int = 10
    relevance_threshold: int = 40


@dataclass
class MonitorConfig:
    max_searches_per_competitor: int = 5


@dataclass
class LookoutConfig:
    company: CompanyConfig
    market: MarketConfig
    competitors: list[Competitor]
    email: EmailConfig
    radar: RadarConfig = field(default_factory=RadarConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)


def load_config(path: str | Path) -> LookoutConfig:
    """Load and validate a YAML config file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError("Config file is empty")

    # Parse company
    company_raw = raw.get("company", {})
    company = CompanyConfig(
        name=company_raw["name"],
        description=company_raw["description"],
        website=company_raw.get("website", ""),
        competitive_wedge=company_raw.get("competitive_wedge", ""),
    )

    # Parse market
    market_raw = raw.get("market", {})
    market = MarketConfig(
        definition=market_raw["definition"],
        primary_keywords=market_raw.get("primary_keywords", []),
        negative_keywords=market_raw.get("negative_keywords", []),
        icp_overlap_signals=market_raw.get("icp_overlap_signals", []),
    )

    # Parse competitors
    competitors = []
    for c in raw.get("competitors", []):
        competitors.append(
            Competitor(
                name=c["name"],
                website=c.get("website", ""),
                track=c.get("track", ["pricing", "features", "jobs", "funding", "messaging"]),
            )
        )

    # Parse email
    email_raw = raw.get("email", {})
    email = EmailConfig(
        to=email_raw.get("to", ""),
        from_addr=email_raw.get("from", ""),
        subject_prefix=email_raw.get("subject_prefix", "[Lookout]"),
    )

    # Parse radar
    radar_raw = raw.get("radar", {})
    radar = RadarConfig(
        max_searches=radar_raw.get("max_searches", 10),
        relevance_threshold=radar_raw.get("relevance_threshold", 40),
    )

    # Parse monitor
    monitor_raw = raw.get("monitor", {})
    monitor = MonitorConfig(
        max_searches_per_competitor=monitor_raw.get("max_searches_per_competitor", 5),
    )

    return LookoutConfig(
        company=company,
        market=market,
        competitors=competitors,
        email=email,
        radar=radar,
        monitor=monitor,
    )
