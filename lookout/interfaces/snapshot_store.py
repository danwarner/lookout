"""ABC for snapshot persistence."""

from abc import ABC, abstractmethod

from lookout.domain.entities import Snapshot


class SnapshotStore(ABC):
    """Persists competitor snapshots between runs."""

    @abstractmethod
    def save(self, snapshot: Snapshot) -> None:
        """Save a snapshot for a competitor."""
        ...

    @abstractmethod
    def load_latest(self, competitor_name: str) -> Snapshot | None:
        """Load the most recent snapshot for a competitor.

        Returns None if no previous snapshot exists.
        """
        ...
