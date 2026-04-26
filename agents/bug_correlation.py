"""
agents/bug_correlation.py

Fetches closed bug-labelled issues from the GitHub REST API (no auth required
for public repos — 60 req/hour limit) and correlates their open/close dates
with the velocity time windows to produce a per-window bug density signal.

Returns an empty list gracefully when:
  - repo is not on GitHub
  - network is unavailable
  - API rate limit is exceeded
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

try:
    from models import VelocityWindow, BugDensityRecord
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import VelocityWindow, BugDensityRecord

logger = logging.getLogger(__name__)

_GH_RE = re.compile(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", re.IGNORECASE)
_BUG_LABELS = {"bug", "bug report", "defect", "regression", "crash", "error", "type: bug"}
_API_BASE = "https://api.github.com"
_HEADERS = {"User-Agent": "debt-archaeologist/1.0", "Accept": "application/vnd.github.v3+json"}


def _parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _gh_get(url: str) -> Optional[list]:
    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=12) as resp:
            if resp.status == 200:
                return json.loads(resp.read())
    except URLError as exc:
        logger.debug("GitHub API error: %s", exc)
    return None


class BugCorrelationAgent:
    """Stateless agent — returns [] when GitHub data is unavailable."""

    def analyse(
        self,
        repo_url: str,
        velocity_windows: list[VelocityWindow],
    ) -> list[BugDensityRecord]:
        if not velocity_windows:
            return []

        m = _GH_RE.search(repo_url)
        if not m:
            logger.debug("Not a GitHub URL — skipping bug correlation")
            return []

        owner_repo = m.group(1)
        issues = self._fetch_bugs(owner_repo)
        if not issues:
            return []

        logger.info("Bug correlation: %d closed bug issues fetched", len(issues))
        return self._correlate(issues, velocity_windows)

    def _fetch_bugs(self, owner_repo: str) -> list[dict]:
        """Fetch up to 500 closed issues with bug-like labels."""
        issues: list[dict] = []
        for page in range(1, 6):
            url = (
                f"{_API_BASE}/repos/{owner_repo}/issues"
                f"?state=closed&per_page=100&page={page}"
            )
            batch = _gh_get(url)
            if not batch:
                break
            # Filter to bug-labelled issues (pull_requests have a 'pull_request' key)
            for item in batch:
                if "pull_request" in item:
                    continue
                labels = {lbl["name"].lower() for lbl in item.get("labels", [])}
                if labels & _BUG_LABELS:
                    issues.append(item)
            if len(batch) < 100:
                break
        return issues

    def _correlate(
        self,
        issues: list[dict],
        windows: list[VelocityWindow],
    ) -> list[BugDensityRecord]:
        records = []
        for vel in windows:
            opened = closed = 0
            for issue in issues:
                created = _parse_dt(issue.get("created_at", ""))
                if created and vel.window_start <= created <= vel.window_end:
                    opened += 1
                if issue.get("closed_at"):
                    closed_dt = _parse_dt(issue["closed_at"])
                    if closed_dt and vel.window_start <= closed_dt <= vel.window_end:
                        closed += 1
            records.append(BugDensityRecord(
                window_start=vel.window_start,
                window_end=vel.window_end,
                bugs_opened=opened,
                bugs_closed=closed,
                net_bugs=opened - closed,
            ))
        return records
