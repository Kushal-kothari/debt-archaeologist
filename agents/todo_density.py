"""
agents/todo_density.py

Tracks TODO / FIXME / HACK / XXX density over time using actual diff data
populated by the ingestion layer (CommitRecord.todo_added / todo_removed).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from models import CommitRecord, TodoEntry, TodoDensityRecord
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import CommitRecord, TodoEntry, TodoDensityRecord


_TAG_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)


def _month_bucket(dt: datetime) -> datetime:
    """Truncate a datetime to the first of its month (UTC)."""
    return datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)


class TodoDensityAgent:
    """
    Stateless agent.  Call :meth:`analyse` with all commits; returns
    a list of :class:`TodoDensityRecord` sorted by window_start.
    """

    def analyse(
        self,
        commits: list[CommitRecord],
        window_days: int = 30,
    ) -> list[TodoDensityRecord]:
        """Bucket commits into *window_days*-wide windows and compute density."""
        if not commits:
            return []

        # Build windows aligned to the earliest authored date across all commits
        start = min(c.authored_date for c in commits).replace(hour=0, minute=0, second=0, microsecond=0)
        end = max(c.authored_date for c in commits)

        windows: list[tuple[datetime, datetime]] = []
        cursor = start
        delta = timedelta(days=window_days)
        while cursor <= end:
            windows.append((cursor, cursor + delta))
            cursor += delta

        # Count tags per window from actual diff data
        window_counts: dict[int, dict[str, int]] = defaultdict(lambda: {"new": 0, "resolved": 0})

        for commit in commits:
            if commit.todo_added == 0 and commit.todo_removed == 0:
                continue
            idx = int((commit.authored_date - start).total_seconds() // (window_days * 86400))
            idx = max(0, min(idx, len(windows) - 1))
            window_counts[idx]["new"] += commit.todo_added
            window_counts[idx]["resolved"] += commit.todo_removed

        records: list[TodoDensityRecord] = []
        running_total = 0
        for i, (ws, we) in enumerate(windows):
            new = window_counts[i]["new"]
            resolved = window_counts[i].get("resolved", 0)
            running_total += new - resolved
            density = new / max(1, (we - ws).days)
            records.append(
                TodoDensityRecord(
                    window_start=ws,
                    window_end=we,
                    total_todos=running_total,
                    new_todos=new,
                    resolved_todos=resolved,
                    density_score=round(density, 4),
                )
            )

        return records
