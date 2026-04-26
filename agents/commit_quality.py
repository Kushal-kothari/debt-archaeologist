"""
agents/commit_quality.py

Scores commits with fast heuristics — no LLM calls.
The LLM budget is spent once in the synthesis layer where it has the full picture.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    from models import CommitRecord, CommitQualityScore
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import CommitRecord, CommitQualityScore

_LOW_QUALITY_RE = re.compile(
    r"^\s*(wip|temp|tmp|fixup!|squash!|fix|update|changes|misc|stuff|oops|typo|cleanup)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_GENERATED_EXTENSIONS = {".min.js", ".min.css", ".pb", ".lock", ".sum", ".pyc"}
_HIGH_CHURN = 500


class CommitQualityAgent:
    def score_all(self, commits: list[CommitRecord]) -> list[CommitQualityScore]:
        return [_score(c) for c in commits if not _is_merge(c)]


def _is_merge(commit: CommitRecord) -> bool:
    msg = commit.message.lower()
    return msg.startswith("merge ") or msg.startswith("merge pull request")


def _score(commit: CommitRecord) -> CommitQualityScore:
    reasons: list[str] = []
    penalty = 0.0
    subject = commit.message.strip().splitlines()[0] if commit.message.strip() else ""

    if _LOW_QUALITY_RE.match(subject):
        penalty += 0.40
        reasons.append("Vague commit message")
    if len(subject) < 10:
        penalty += 0.20
        reasons.append("Subject too short")
    if len(subject) > 72:
        penalty += 0.10
        reasons.append("Subject exceeds 72 chars")
    if commit.churn > _HIGH_CHURN:
        penalty += 0.15
        reasons.append(f"Very high churn ({commit.churn} lines)")
    if commit.files_changed and all(
        any(f.endswith(ext) for ext in _GENERATED_EXTENSIONS)
        for f in commit.files_changed
    ):
        penalty += 0.10
        reasons.append("Only generated/lock files changed")

    return CommitQualityScore(
        sha=commit.sha,
        score=max(0.0, round(1.0 - penalty, 3)),
        reasons=reasons,
        authored_date=commit.authored_date,
    )
