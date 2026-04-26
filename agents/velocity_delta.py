"""
agents/velocity_delta.py

Measures development velocity over rolling time windows and detects
sudden slowdowns (velocity drops) that often correlate with debt accumulation.

Velocity score (0–1):
    normalized commit frequency × inverse average churn magnitude
    → high score = many small, frequent commits (healthy)
    → low score  = infrequent or gigantic commits (risky)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from models import CommitRecord, VelocityWindow
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import CommitRecord, VelocityWindow


class VelocityDeltaAgent:
    """
    Stateless agent.  Bucket commits into windows and compute velocity.
    """

    def analyse(
        self,
        commits: list[CommitRecord],
        window_days: int = 14,
    ) -> list[VelocityWindow]:
        if not commits:
            return []

        start = min(c.authored_date for c in commits).replace(hour=0, minute=0, second=0, microsecond=0)
        end = max(c.authored_date for c in commits)
        delta = timedelta(days=window_days)

        # Build windows
        windows: list[tuple[datetime, datetime]] = []
        cursor = start
        while cursor <= end:
            windows.append((cursor, cursor + delta))
            cursor += delta

        # Bucket commits
        bucketed: list[list[CommitRecord]] = [[] for _ in windows]
        for commit in commits:
            idx = int((commit.authored_date - start).total_seconds() // (window_days * 86400))
            idx = max(0, min(idx, len(windows) - 1))
            bucketed[idx].append(commit)

        # Raw velocity per window
        raw_velocities: list[float] = []
        for i, (ws, we) in enumerate(windows):
            bucket = bucketed[i]
            count = len(bucket)
            avg_churn = sum(c.churn for c in bucket) / max(count, 1)
            # Frequency component: commits per day
            freq = count / window_days
            # Churn penalty: large churns lower score
            churn_factor = 1.0 / (1.0 + avg_churn / 200.0)
            raw_velocities.append(freq * churn_factor)

        # Normalize to 0–1
        max_v = max(raw_velocities) if raw_velocities else 1.0
        max_v = max_v or 1.0

        records: list[VelocityWindow] = []
        for i, (ws, we) in enumerate(windows):
            bucket = bucketed[i]
            count = len(bucket)
            avg_churn = sum(c.churn for c in bucket) / max(count, 1)
            records.append(
                VelocityWindow(
                    window_start=ws,
                    window_end=we,
                    commit_count=count,
                    avg_churn_per_commit=round(avg_churn, 1),
                    velocity_score=round(raw_velocities[i] / max_v, 4),
                )
            )

        return records
