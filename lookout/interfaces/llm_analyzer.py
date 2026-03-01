"""ABC for LLM analysis capabilities."""

from abc import ABC, abstractmethod

from lookout.domain.entities import Change, Signal


class LLMAnalyzer(ABC):
    """Provides LLM-powered analysis: scoring, diffing, summarizing."""

    @abstractmethod
    def score_relevance(
        self,
        company_info: dict,
        company_description: str,
        market_definition: str,
        icp_signals: list[str],
    ) -> Signal:
        """Score a discovered company's relevance to our market.

        Returns a Signal with relevance_score, threat_level, reasoning.
        """
        ...

    @abstractmethod
    def analyze_diff(
        self,
        competitor_name: str,
        previous_snapshot: dict,
        current_snapshot: dict,
        prev_date: str,
        curr_date: str,
    ) -> list[Change]:
        """Compare two snapshots and identify meaningful changes.

        Returns a list of Change objects for significant differences.
        """
        ...

    @abstractmethod
    def summarize_digest(
        self,
        radar_signals: list[Signal],
        monitor_diffs: list,
        company_description: str,
        competitive_wedge: str = "",
        icp_signals: list[str] | None = None,
        historical_changes: str = "",
    ) -> str:
        """Generate a brief executive summary of all findings.

        When competitive_wedge is provided, includes a Competitive Wedge Analysis section.
        When historical_changes is provided, weaves context about what changed since last scan.
        """
        ...
