"""Discover unknown competitors via radar scan."""

from __future__ import annotations

from lookout.domain.entities import Signal
from lookout.infrastructure.anthropic_analyzer import AnthropicAnalyzer
from lookout.interfaces.search_provider import SearchProvider


def run_radar_scan(
    searcher: SearchProvider,
    analyzer: AnthropicAnalyzer,
    keywords: list[str],
    market_definition: str,
    company_description: str,
    icp_signals: list[str],
    negative_keywords: list[str],
    max_searches: int = 10,
    relevance_threshold: int = 40,
) -> list[Signal]:
    """Discover and score unknown competitors.

    Pipeline: search → extract companies → score relevance → filter → return.
    """
    # Phase 1: Search the market using Claude + web_search
    raw_results = searcher.search_market(keywords, market_definition, max_searches=max_searches)

    # Phase 2: Score all discovered companies against our market
    all_signals: list[Signal] = []
    for result in raw_results:
        raw_text = result.get("raw_response", "")
        if not raw_text:
            continue

        signals = analyzer.score_relevance_batch(
            raw_response=raw_text,
            company_description=company_description,
            market_definition=market_definition,
            icp_signals=icp_signals,
            negative_keywords=negative_keywords,
        )
        all_signals.extend(signals)

    # Filter by relevance threshold and deduplicate by name
    seen_names: set[str] = set()
    filtered: list[Signal] = []
    for signal in sorted(all_signals, key=lambda s: s.relevance_score, reverse=True):
        name_key = signal.name.lower().strip()
        if name_key in seen_names:
            continue
        if signal.relevance_score >= relevance_threshold:
            seen_names.add(name_key)
            filtered.append(signal)

    return filtered
