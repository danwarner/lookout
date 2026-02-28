"""Monitor known competitors for changes."""

from __future__ import annotations

from datetime import datetime

from lookout.domain.entities import Competitor, Diff, Snapshot
from lookout.infrastructure.anthropic_analyzer import AnthropicAnalyzer
from lookout.interfaces.search_provider import SearchProvider
from lookout.interfaces.snapshot_store import SnapshotStore


def run_monitor_scan(
    searcher: SearchProvider,
    analyzer: AnthropicAnalyzer,
    snapshot_store: SnapshotStore,
    competitors: list[Competitor],
    max_searches_per_competitor: int = 5,
) -> list[Diff]:
    """Check known competitors for changes.

    Pipeline per competitor: search → structure → snapshot → diff → results.
    """
    diffs: list[Diff] = []

    for competitor in competitors:
        # Phase 1: Gather current intel via Claude + web_search
        raw_intel = searcher.gather_competitor_intel(
            competitor_name=competitor.name,
            website=competitor.website,
            track_sections=competitor.track,
            max_searches=max_searches_per_competitor,
        )

        # Phase 2: Structure the raw intel into sections
        search_result_urls = raw_intel.get("search_result_urls", [])
        current_sections = analyzer.structure_intel(
            raw_intel=raw_intel.get("raw_intel", ""),
            competitor_name=competitor.name,
            track_sections=competitor.track,
            search_result_urls=search_result_urls if search_result_urls else None,
        )

        # Create current snapshot
        now = datetime.now().isoformat()
        current_snapshot = Snapshot(
            competitor=competitor.name,
            timestamp=now,
            sections=current_sections,
        )

        # Load previous snapshot for diffing
        previous_snapshot = snapshot_store.load_latest(competitor.name)

        if previous_snapshot is not None:
            # Phase 3: Analyze diff between snapshots
            changes = analyzer.analyze_diff(
                competitor_name=competitor.name,
                previous_snapshot=previous_snapshot.sections,
                current_snapshot=current_sections,
                prev_date=previous_snapshot.timestamp,
                curr_date=now,
            )
            diffs.append(Diff(competitor_name=competitor.name, changes=changes))
        else:
            # First scan — no diff, just record baseline
            diffs.append(Diff(competitor_name=competitor.name, changes=[]))

        # Save current snapshot (becomes the new baseline)
        snapshot_store.save(current_snapshot)

    return diffs


def run_single_monitor(
    searcher: SearchProvider,
    analyzer: AnthropicAnalyzer,
    snapshot_store: SnapshotStore,
    competitor: Competitor,
    max_searches: int = 5,
) -> Diff:
    """Monitor a single competitor. Convenience wrapper."""
    results = run_monitor_scan(
        searcher=searcher,
        analyzer=analyzer,
        snapshot_store=snapshot_store,
        competitors=[competitor],
        max_searches_per_competitor=max_searches,
    )
    return results[0]
