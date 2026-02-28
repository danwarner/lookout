"""Relevance scoring thresholds and threat level classification."""

from lookout.domain.entities import ThreatLevel


# Relevance score thresholds
HIGH_RELEVANCE_THRESHOLD = 70
MEDIUM_RELEVANCE_THRESHOLD = 40

# Default minimum score to include in results
DEFAULT_RELEVANCE_THRESHOLD = 40


def classify_threat(relevance_score: int) -> ThreatLevel:
    """Classify threat level based on relevance score."""
    if relevance_score >= HIGH_RELEVANCE_THRESHOLD:
        return ThreatLevel.HIGH
    elif relevance_score >= MEDIUM_RELEVANCE_THRESHOLD:
        return ThreatLevel.MEDIUM
    return ThreatLevel.LOW
