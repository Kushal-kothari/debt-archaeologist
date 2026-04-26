"""
agents/file_churn.py

Computes per-file churn rates across all commits.

Churn score formula:
    churn_score = total_lines_changed * log(1 + total_commits)

High churn + high commit count → frequently rewritten → likely debt hotspot.
"""

from __future__ import annotations

import math
from pathlib import Path

try:
    from models import CommitRecord, FileChurnRecord
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import CommitRecord, FileChurnRecord


class FileChurnAgent:
    """
    Stateless agent.  Feed it all CommitRecord objects and get back a list
    of FileChurnRecord sorted by churn_score descending.
    """

    def analyse(self, commits: list[CommitRecord], top_n: int = 50) -> list[FileChurnRecord]:
        """Return the *top_n* most-churned files."""
        tally: dict[str, dict] = {}

        for commit in commits:
            churn_per_file = commit.churn // max(len(commit.files_changed), 1)
            for filepath in commit.files_changed:
                entry = tally.setdefault(filepath, {"commits": 0, "lines": 0})
                entry["commits"] += 1
                entry["lines"] += churn_per_file

        records = [
            FileChurnRecord(
                filepath=fp,
                total_commits=data["commits"],
                total_lines_changed=data["lines"],
                churn_score=round(data["lines"] * math.log1p(data["commits"]), 2),
            )
            for fp, data in tally.items()
        ]

        records.sort(key=lambda r: r.churn_score, reverse=True)
        return records[:top_n]
