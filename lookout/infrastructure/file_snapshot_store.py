"""JSON file-based snapshot persistence."""

from __future__ import annotations

import json
from pathlib import Path

from lookout.domain.entities import Snapshot
from lookout.interfaces.snapshot_store import SnapshotStore


def _sanitize_name(name: str) -> str:
    """Convert a competitor name to a safe filename."""
    return name.lower().replace(" ", "_").replace("/", "_")


class FileSnapshotStore(SnapshotStore):
    """Persists snapshots as JSON files in a directory."""

    def __init__(self, directory: str | Path = "snapshots"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: Snapshot) -> None:
        safe_name = _sanitize_name(snapshot.competitor)
        # Save as latest (overwriting previous)
        latest_path = self.directory / f"{safe_name}_latest.json"
        data = {
            "competitor": snapshot.competitor,
            "timestamp": snapshot.timestamp,
            "sections": snapshot.sections,
        }
        with open(latest_path, "w") as f:
            json.dump(data, f, indent=2)

        # Also save a timestamped copy for history
        ts = snapshot.timestamp.replace(":", "-").replace(".", "-")
        history_path = self.directory / f"{safe_name}_{ts}.json"
        with open(history_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_latest(self, competitor_name: str) -> Snapshot | None:
        safe_name = _sanitize_name(competitor_name)
        latest_path = self.directory / f"{safe_name}_latest.json"

        if not latest_path.exists():
            return None

        with open(latest_path) as f:
            data = json.load(f)

        return Snapshot(
            competitor=data["competitor"],
            timestamp=data["timestamp"],
            sections=data.get("sections", {}),
        )
