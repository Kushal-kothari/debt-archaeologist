"""
main.py - Orchestration entry point for the Technical Debt Archaeologist.

Agents run in parallel via LangGraph, then two sequential post-processing
steps (code complexity + bug correlation) run before synthesis.

Usage:
    python main.py --repo https://github.com/django/django --max-commits 500
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from tempfile import gettempdir
from typing import TypedDict

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()

from ingestion.ingest import ingest_repo
from agents.commit_quality import CommitQualityAgent
from agents.file_churn import FileChurnAgent
from agents.todo_density import TodoDensityAgent
from agents.pr_pattern import PRPatternAgent
from agents.velocity_delta import VelocityDeltaAgent
from agents.code_complexity import CodeComplexityAgent
from agents.bug_correlation import BugCorrelationAgent
from synthesis.synthesizer import SynthesisAgent

try:
    from langgraph.graph import StateGraph, END
    try:
        from langgraph.graph import START
    except ImportError:
        START = "__start__"
    _LANGGRAPH = True
except ImportError:
    _LANGGRAPH = False

console = Console()
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


# ---------------------------------------------------------------------------
# LangGraph parallel state (Phase A agents)
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    commits: list
    local_path: str
    quality_scores: list
    churn_records: list
    todo_windows: list
    pr_patterns: list
    velocity_windows: list


def _quality_node(state: AgentState) -> dict:
    scores = CommitQualityAgent().score_all(state["commits"])
    console.print(f"  [OK]  Commit quality  - {len(scores)} scores")
    return {"quality_scores": scores}

def _churn_node(state: AgentState) -> dict:
    records = FileChurnAgent().analyse(state["commits"], top_n=50)
    console.print(f"  [OK]  File churn      - {len(records)} files ranked")
    return {"churn_records": records}

def _todo_node(state: AgentState) -> dict:
    windows = TodoDensityAgent().analyse(state["commits"], window_days=30)
    console.print(f"  [OK]  TODO density    - {len(windows)} monthly windows")
    return {"todo_windows": windows}

def _pr_node(state: AgentState) -> dict:
    patterns = PRPatternAgent().analyse(state["commits"])
    console.print(f"  [OK]  PR patterns     - {len(patterns)} merge events")
    return {"pr_patterns": patterns}

def _velocity_node(state: AgentState) -> dict:
    windows = VelocityDeltaAgent().analyse(state["commits"], window_days=14)
    console.print(f"  [OK]  Velocity delta  - {len(windows)} bi-weekly windows")
    return {"velocity_windows": windows}


def _build_graph():
    builder = StateGraph(AgentState)
    for name, fn in [
        ("quality",  _quality_node),
        ("churn",    _churn_node),
        ("todo",     _todo_node),
        ("pr",       _pr_node),
        ("velocity", _velocity_node),
    ]:
        builder.add_node(name, fn)
        builder.add_edge(START, name)
        builder.add_edge(name, END)
    return builder.compile()


def _run_phase_a(commits: list, local_path: str) -> AgentState:
    """Phase A: 5 parallel agents via LangGraph (or sequential fallback)."""
    init = AgentState(
        commits=commits, local_path=local_path,
        quality_scores=[], churn_records=[], todo_windows=[],
        pr_patterns=[], velocity_windows=[],
    )
    if _LANGGRAPH:
        return _build_graph().invoke(init)
    return AgentState(
        **init,
        quality_scores=_quality_node(init)["quality_scores"],
        churn_records=_churn_node(init)["churn_records"],
        todo_windows=_todo_node(init)["todo_windows"],
        pr_patterns=_pr_node(init)["pr_patterns"],
        velocity_windows=_velocity_node(init)["velocity_windows"],
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(
    repo_url: str,
    max_commits: int = 500,
    output_path: Path | None = None,
) -> None:
    repo_name  = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    local_path = Path(gettempdir()) / f"debt-arch-{repo_name}"

    console.print(Panel(
        f"[bold cyan]Technical Debt Archaeologist[/bold cyan]\n"
        f"Repo   : [yellow]{repo_url}[/yellow]\n"
        f"Cache  : [dim]{local_path}[/dim]\n"
        f"Commits: up to {max_commits}",
        expand=False,
    ))

    # ── Step 1: Ingest ────────────────────────────────────────────────────────
    console.print("\n[bold]Step 1/4  Ingesting commit history ...[/bold]")
    commits = ingest_repo(
        repo_url=repo_url,
        local_path=local_path,
        max_commits=max_commits,
        branch="main",
    )
    console.print(f"  [OK]  {len(commits)} commits loaded.")

    # ── Step 2: Phase A agents (parallel) ────────────────────────────────────
    mode = "parallel via LangGraph" if _LANGGRAPH else "sequential"
    console.print(f"\n[bold]Step 2/4  Running history agents ({mode}) ...[/bold]")
    state = _run_phase_a(commits, str(local_path))

    # ── Step 3: Phase B agents (sequential — need Phase A outputs) ────────────
    console.print("\n[bold]Step 3/4  Running deep analysis ...[/bold]")

    code_records = CodeComplexityAgent().analyse(local_path)
    console.print(f"  [OK]  Code complexity - {len(code_records)} files analysed")

    bug_records = BugCorrelationAgent().analyse(repo_url, state["velocity_windows"])
    console.print(f"  [OK]  Bug correlation - {len(bug_records)} windows correlated")

    # ── Step 4: Synthesis ─────────────────────────────────────────────────────
    console.print("\n[bold]Step 4/4  Synthesising debt events ...[/bold]")
    result = SynthesisAgent().synthesize(
        repo_url=repo_url,
        repo_name=repo_name,
        quality_scores=state["quality_scores"],
        churn_records=state["churn_records"],
        todo_windows=state["todo_windows"],
        pr_patterns=state["pr_patterns"],
        velocity_windows=state["velocity_windows"],
        code_records=code_records,
        bug_records=bug_records,
        commits=commits,
    )

    console.print(f"\n  [green bold]Analysis complete![/green bold]")
    console.print(f"  Overall debt score      : [red]{result.overall_debt_score}/100[/red]")
    if result.benchmark_percentile is not None:
        console.print(f"  Benchmark percentile    : top {100 - result.benchmark_percentile:.0f}% of repos")
    if result.overall_complexity_score is not None:
        console.print(f"  Code complexity score   : {result.overall_complexity_score:.2f}/1.0")
    console.print(f"  Debt events found       : {len(result.debt_events)}")

    if output_path is None:
        output_path = Path(f"debt_report_{repo_name}.json")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(result.model_dump_json(indent=2))

    console.print(f"\n  Report saved -> [cyan]{output_path}[/cyan]")
    console.print("\n  Run the dashboard:\n  [bold]python -m streamlit run dashboard/app.py[/bold]\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Technical Debt Archaeologist")
    parser.add_argument("--repo", default="https://github.com/django/django.git",
                        help="Remote Git URL to analyse")
    parser.add_argument("--max-commits", type=int, default=500, dest="max_commits")
    parser.add_argument("--output", type=Path, default=None,
                        help="Path for the JSON report")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(repo_url=args.repo, max_commits=args.max_commits, output_path=args.output)
