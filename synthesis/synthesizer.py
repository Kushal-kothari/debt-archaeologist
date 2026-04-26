"""
synthesis/synthesizer.py

Merges all agent outputs into DebtEvent objects with:
  - Per-window quality averages, PR counts, bug density
  - Author-level debt attribution
  - Benchmark percentile vs reference repos
  - Single gpt-4o-mini call for executive summary + top-window hints
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from models import (
        CommitRecord, CommitQualityScore, FileChurnRecord,
        TodoDensityRecord, PRPattern, VelocityWindow,
        CodeComplexityRecord, BugDensityRecord,
        DebtEvent, DebtSeverity, AnalysisResult,
        AuthorDebtRecord,
    )
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import (
        CommitRecord, CommitQualityScore, FileChurnRecord,
        TodoDensityRecord, PRPattern, VelocityWindow,
        CodeComplexityRecord, BugDensityRecord,
        DebtEvent, DebtSeverity, AnalysisResult,
        AuthorDebtRecord,
    )

logger = logging.getLogger(__name__)

_BENCH_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "reference_scores.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity(score: float) -> DebtSeverity:
    if score >= 75: return DebtSeverity.CRITICAL
    if score >= 50: return DebtSeverity.HIGH
    if score >= 25: return DebtSeverity.MEDIUM
    return DebtSeverity.LOW


def _event_id(ps: datetime, pe: datetime) -> str:
    return hashlib.md5(f"{ps.isoformat()}-{pe.isoformat()}".encode()).hexdigest()[:12]


def _pr_counts(pr_patterns: list[PRPattern], windows: list[VelocityWindow]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for pr in pr_patterns:
        if pr.authored_date is None:
            continue
        for i, vel in enumerate(windows):
            if vel.window_start <= pr.authored_date <= vel.window_end:
                counts[i] += 1
                break
    return dict(counts)


def _bug_counts(bug_records: list[BugDensityRecord], windows: list[VelocityWindow]) -> dict[int, int]:
    out: dict[int, int] = {}
    for i, vel in enumerate(windows):
        for br in bug_records:
            if br.window_start == vel.window_start:
                out[i] = br.bugs_opened
                break
    return out


def _author_records(
    commits: list[CommitRecord],
    quality_scores: list[CommitQualityScore],
) -> list[AuthorDebtRecord]:
    sha_score = {s.sha: s.score for s in quality_scores}
    data: dict[str, dict] = defaultdict(lambda: {
        "name": "", "commits": 0, "q_sum": 0.0, "high_churn": 0, "todos": 0
    })
    for c in commits:
        d = data[c.author_email]
        d["name"]       = c.author_name
        d["commits"]    += 1
        d["q_sum"]      += sha_score.get(c.sha, 0.7)
        d["high_churn"] += 1 if c.churn > 500 else 0
        d["todos"]      += c.todo_added

    records = []
    for email, d in data.items():
        if d["commits"] < 3:
            continue
        avg_q = d["q_sum"] / d["commits"]
        score = min(1.0, round(
            (1 - avg_q) * 0.5 + min(d["high_churn"] / max(d["commits"], 1), 1.0) * 0.3
            + min(d["todos"] / 20.0, 1.0) * 0.2,
            3,
        ))
        records.append(AuthorDebtRecord(
            author_name=d["name"],
            author_email=email,
            commit_count=d["commits"],
            avg_quality_score=round(avg_q, 3),
            high_churn_commits=d["high_churn"],
            todo_introduced=d["todos"],
            debt_contribution_score=score,
        ))
    return sorted(records, key=lambda r: r.debt_contribution_score, reverse=True)


def _benchmark_percentile(debt_score: float) -> Optional[float]:
    """Return percentile rank (0-100) vs reference repos. Lower = less debt."""
    try:
        data = json.loads(_BENCH_PATH.read_text())
        thresholds = sorted(data["debt_score"].items(), key=lambda x: float(x[1]))
        for label, val in thresholds:
            if debt_score <= float(val):
                return float(label.replace("p", ""))
        return 99.0
    except Exception:
        return None


def _heuristic_hints(vel: VelocityWindow, avg_quality: float, todo_delta: int) -> list[str]:
    hints = []
    if vel.velocity_score < 0.2:
        hints.append("Very low commit velocity — possible team bottleneck or blocked refactor.")
    if avg_quality < 0.4:
        hints.append("Many vague or oversized commits — enforce conventional commits and PR size limits.")
    if todo_delta > 5:
        hints.append(f"{todo_delta} new TODO/FIXME annotations — schedule a debt-clearing sprint.")
    if vel.avg_churn_per_commit > 300:
        hints.append("Large average churn per commit — consider splitting work into smaller PRs.")
    return hints


# ---------------------------------------------------------------------------
# Synthesis agent
# ---------------------------------------------------------------------------

class SynthesisAgent:
    def __init__(self, openai_api_key: Optional[str] = None):
        key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._client = None
        if key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=key)
            except ImportError:
                logger.warning("openai not installed — skipping LLM synthesis")

    def synthesize(
        self,
        *,
        repo_url: str,
        repo_name: str,
        quality_scores: list[CommitQualityScore],
        churn_records: list[FileChurnRecord],
        todo_windows: list[TodoDensityRecord],
        pr_patterns: list[PRPattern],
        velocity_windows: list[VelocityWindow],
        code_records: Optional[list[CodeComplexityRecord]] = None,
        bug_records: Optional[list[BugDensityRecord]] = None,
        commits: Optional[list[CommitRecord]] = None,
    ) -> AnalysisResult:
        code_records = code_records or []
        bug_records  = bug_records  or []
        commits      = commits      or []

        top_churned  = [r.filepath for r in churn_records[:5]]
        pr_cnt       = _pr_counts(pr_patterns, velocity_windows)
        bug_cnt      = _bug_counts(bug_records, velocity_windows)
        events: list[DebtEvent] = []

        for i, vel in enumerate(velocity_windows):
            # Per-window quality average
            wq = [
                s.score for s in quality_scores
                if s.authored_date and vel.window_start <= s.authored_date <= vel.window_end
            ]
            avg_quality = (sum(wq) / len(wq)) if wq else (
                sum(s.score for s in quality_scores) / len(quality_scores) if quality_scores else 0.5
            )

            todo_delta = 0
            for tw in todo_windows:
                if tw.window_start <= vel.window_start <= tw.window_end:
                    todo_delta = tw.new_todos - tw.resolved_todos
                    break

            bugs = bug_cnt.get(i, 0)

            # Composite debt score
            debt_score = (
                (1.0 - vel.velocity_score) * 25
                + (1.0 - avg_quality) * 25
                + min(todo_delta * 2, 15)
                + min(vel.avg_churn_per_commit / 50, 15)
                + min(bugs * 2, 20)
            )

            events.append(DebtEvent(
                event_id=_event_id(vel.window_start, vel.window_end),
                period_start=vel.window_start,
                period_end=vel.window_end,
                severity=_severity(debt_score),
                debt_score=round(debt_score, 1),
                commit_quality_avg=round(avg_quality, 3),
                top_churned_files=top_churned,
                todo_delta=todo_delta,
                velocity_score=vel.velocity_score,
                pr_merge_count=pr_cnt.get(i, 0),
                bug_count=bugs,
                summary=(
                    f"Window {vel.window_start.date()} -> {vel.window_end.date()}: "
                    f"{vel.commit_count} commits, avg churn {vel.avg_churn_per_commit:.0f} lines, "
                    f"velocity {vel.velocity_score:.2f}, +{todo_delta} TODOs, {bugs} bugs opened."
                ),
                remediation_hints=_heuristic_hints(vel, avg_quality, todo_delta),
            ))

        overall = sum(e.debt_score for e in events) / len(events) if events else 0.0
        perc     = _benchmark_percentile(overall)
        avg_cc   = (
            sum(r.avg_cyclomatic_complexity for r in code_records) / len(code_records)
            if code_records else None
        )
        overall_complexity = (
            sum(r.complexity_score for r in code_records) / len(code_records)
            if code_records else None
        )
        authors  = _author_records(commits, quality_scores)

        fallback_summary = (
            f"Analysed {len(quality_scores)} commits across {len(events)} windows. "
            f"Overall debt score: {overall:.1f}/100."
        )

        if self._client and events:
            events, summary = self._enhance_with_llm(
                events, repo_name, overall, perc, avg_cc, fallback_summary
            )
        else:
            summary = fallback_summary

        return AnalysisResult(
            repo_url=repo_url,
            repo_name=repo_name,
            analysis_timestamp=datetime.now(tz=timezone.utc),
            total_commits_analyzed=len(quality_scores),
            debt_events=events,
            overall_debt_score=round(overall, 1),
            executive_summary=summary,
            code_complexity=code_records[:20],
            author_records=authors[:20],
            bug_density=bug_records,
            overall_complexity_score=round(overall_complexity, 3) if overall_complexity else None,
            benchmark_percentile=perc,
        )

    def _enhance_with_llm(
        self,
        events: list[DebtEvent],
        repo_name: str,
        overall: float,
        percentile: Optional[float],
        avg_cc: Optional[float],
        fallback: str,
    ) -> tuple[list[DebtEvent], str]:
        worst = sorted(events, key=lambda e: e.debt_score, reverse=True)[:5]
        rows = [
            f'{e.event_id} {e.period_start.date()}~{e.period_end.date()} '
            f'score={e.debt_score:.0f} vel={e.velocity_score:.2f} '
            f'qual={e.commit_quality_avg:.2f} todos={e.todo_delta} '
            f'bugs={e.bug_count or 0} files={",".join(e.top_churned_files[:2])}'
            for e in worst
        ]
        context = f"Repo:{repo_name} overall_debt:{overall:.1f}/100"
        if percentile:
            context += f" benchmark:p{percentile:.0f}"
        if avg_cc:
            context += f" avg_complexity:{avg_cc:.1f}"

        prompt = (
            f"{context}\nTop debt windows:\n" + "\n".join(rows) + "\n\n"
            'Return JSON only: {"summary":"2 sentences — patterns and what to fix",'
            '"events":[{"id":"...","hint":"one concrete actionable fix"}]}'
        )
        try:
            resp = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=400,
            )
            data = json.loads(resp.choices[0].message.content)
            hmap = {item["id"]: item.get("hint", "") for item in data.get("events", [])}
            enhanced = []
            for e in events:
                h = hmap.get(e.event_id)
                enhanced.append(e.model_copy(update={
                    "remediation_hints": ([h] + e.remediation_hints) if h else e.remediation_hints
                }))
            return enhanced, data.get("summary", fallback)
        except Exception as exc:
            logger.warning("LLM enhancement failed: %s", exc)
            return events, fallback
