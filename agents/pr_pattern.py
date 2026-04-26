"""
agents/pr_pattern.py

Extracts PR / merge patterns from commit messages without hitting the GitHub
API (Phase 1).  Works entirely from commit message text.

Detects:
  - GitHub merge-commit patterns: "Merge pull request #NNN from …"
  - Squash-merge patterns: "(#NNN)" at end of subject
  - Bors / merge-queue bots
  - Estimated days-open (when two linked commits are found with the same PR#)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

try:
    from models import CommitRecord, PRPattern
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import CommitRecord, PRPattern


_MERGE_PR_RE = re.compile(r"Merge pull request #(\d+)", re.IGNORECASE)
_SQUASH_PR_RE = re.compile(r"\(#(\d+)\)\s*$")
_BORS_RE = re.compile(r"^(Auto merge of|bors)", re.IGNORECASE)


class PRPatternAgent:
    """
    Stateless agent.  Returns one PRPattern per commit (merge commits only).
    """

    def analyse(self, commits: list[CommitRecord]) -> list[PRPattern]:
        patterns: list[PRPattern] = []
        for commit in commits:
            pattern = self._extract(commit)
            if pattern:
                patterns.append(pattern)
        return patterns

    def _extract(self, commit: CommitRecord) -> Optional[PRPattern]:
        msg = commit.message.strip()
        subject = msg.splitlines()[0]

        # GitHub standard merge commit
        m = _MERGE_PR_RE.search(msg)
        if m:
            return PRPattern(
                sha=commit.sha,
                is_merge_commit=True,
                pr_number=int(m.group(1)),
                merge_message=subject,
                authored_date=commit.authored_date,
            )

        # Squash merge with (#NNN) suffix
        m = _SQUASH_PR_RE.search(subject)
        if m:
            return PRPattern(
                sha=commit.sha,
                is_merge_commit=False,
                pr_number=int(m.group(1)),
                merge_message=subject,
                authored_date=commit.authored_date,
            )

        # Bors / merge-queue bot
        if _BORS_RE.match(subject):
            return PRPattern(
                sha=commit.sha,
                is_merge_commit=True,
                merge_message=subject,
                authored_date=commit.authored_date,
            )

        return None
