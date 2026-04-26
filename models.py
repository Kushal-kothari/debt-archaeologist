"""
All Pydantic schemas shared across the pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingestion layer
# ---------------------------------------------------------------------------

class CommitRecord(BaseModel):
    """Raw per-commit metadata extracted by the ingestion layer."""

    sha: str
    author_name: str
    author_email: str
    authored_date: datetime
    committed_date: datetime
    message: str
    files_changed: list[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    todo_added: int = 0
    todo_removed: int = 0

    @property
    def churn(self) -> int:
        return self.lines_added + self.lines_removed


# ---------------------------------------------------------------------------
# Per-agent output models
# ---------------------------------------------------------------------------

class CommitQualityScore(BaseModel):
    """Output of the commit quality scorer agent."""

    sha: str
    score: float = Field(ge=0.0, le=1.0, description="0 = terrible, 1 = excellent")
    reasons: list[str] = Field(default_factory=list)
    authored_date: Optional[datetime] = None


class FileChurnRecord(BaseModel):
    """Churn stats for a single file path."""

    filepath: str
    total_commits: int
    total_lines_changed: int
    churn_score: float = Field(ge=0.0, description="Higher = more turbulent")


class TodoEntry(BaseModel):
    """A single TODO/FIXME/HACK annotation found in a commit diff."""

    sha: str
    filepath: str
    line_number: Optional[int] = None
    tag: str  # TODO | FIXME | HACK | XXX
    text: str


class TodoDensityRecord(BaseModel):
    """Aggregate TODO density for a time window."""

    window_start: datetime
    window_end: datetime
    total_todos: int
    new_todos: int
    resolved_todos: int
    density_score: float


class PRPattern(BaseModel):
    """Inferred PR/merge metadata derived from commit messages."""

    sha: str
    is_merge_commit: bool
    pr_number: Optional[int] = None
    merge_message: Optional[str] = None
    days_open_estimate: Optional[float] = None
    authored_date: Optional[datetime] = None


class CodeComplexityRecord(BaseModel):
    """AST-level complexity metrics for a single source file."""

    filepath: str
    language: str = "python"
    avg_cyclomatic_complexity: float
    max_cyclomatic_complexity: int
    avg_function_length: float
    num_functions: int
    import_count: int
    max_nesting_depth: int = 0
    complex_functions: list[str] = Field(default_factory=list)
    complexity_score: float = Field(ge=0.0, le=1.0, description="0=simple, 1=highly complex")


class AuthorDebtRecord(BaseModel):
    """Per-author debt contribution metrics."""

    author_name: str
    author_email: str
    commit_count: int
    avg_quality_score: float
    high_churn_commits: int
    todo_introduced: int
    debt_contribution_score: float = Field(ge=0.0, le=1.0)


class BugDensityRecord(BaseModel):
    """Bug report density per time window (from GitHub Issues)."""

    window_start: datetime
    window_end: datetime
    bugs_opened: int
    bugs_closed: int
    net_bugs: int


class VelocityWindow(BaseModel):
    """Rolling velocity measurement for a time window."""

    window_start: datetime
    window_end: datetime
    commit_count: int
    avg_churn_per_commit: float
    velocity_score: float = Field(description="Normalized 0–1, higher = faster pace")


# ---------------------------------------------------------------------------
# Synthesis layer
# ---------------------------------------------------------------------------

class DebtSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DebtEvent(BaseModel):
    """
    A discrete technical-debt accumulation event synthesized from all
    agent signals.  This is the primary output of the synthesis agent.
    """

    event_id: str
    period_start: datetime
    period_end: datetime
    severity: DebtSeverity
    debt_score: float = Field(ge=0.0, le=100.0)

    # Contributing signals (optional — not every agent fires on every window)
    commit_quality_avg: Optional[float] = None
    top_churned_files: list[str] = Field(default_factory=list)
    todo_delta: Optional[int] = None
    velocity_score: Optional[float] = None
    pr_merge_count: Optional[int] = None
    bug_count: Optional[int] = None           # bugs opened in this window

    summary: str = Field(description="Human-readable explanation of this event")
    remediation_hints: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Top-level container returned by the full pipeline."""

    repo_url: str
    repo_name: str
    analysis_timestamp: datetime
    total_commits_analyzed: int
    debt_events: list[DebtEvent] = Field(default_factory=list)
    overall_debt_score: float = Field(ge=0.0, le=100.0)
    executive_summary: str = ""

    # Extended analysis
    code_complexity: list[CodeComplexityRecord] = Field(default_factory=list)
    author_records: list[AuthorDebtRecord] = Field(default_factory=list)
    bug_density: list[BugDensityRecord] = Field(default_factory=list)
    overall_complexity_score: Optional[float] = None
    benchmark_percentile: Optional[float] = None
