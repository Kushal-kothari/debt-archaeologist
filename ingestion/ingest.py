"""
ingestion/ingest.py

Clones (or updates) a remote Git repository and extracts per-commit metadata
into a list of CommitRecord objects.

Usage:
    from ingestion.ingest import ingest_repo

    records = ingest_repo(
        repo_url="https://github.com/django/django.git",
        local_path="/tmp/django",
        max_commits=500,   # None → all commits
        branch="main",
    )
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

from git import Repo, InvalidGitRepositoryError, GitCommandError
from tqdm import tqdm

# Use absolute import when running as part of the package, fall back to local
try:
    from models import CommitRecord
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import CommitRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_repo(
    repo_url: str,
    local_path: str | Path,
    *,
    max_commits: Optional[int] = None,
    branch: str = "main",
    show_progress: bool = True,
) -> list[CommitRecord]:
    """
    Clone or pull *repo_url* into *local_path*, then walk the commit history
    and return a list of :class:`CommitRecord` sorted oldest → newest.

    Parameters
    ----------
    repo_url:
        HTTPS or SSH URL of the remote repository.
    local_path:
        Directory where the repo will be cloned / already exists.
    max_commits:
        Cap the number of commits to process (most-recent first before
        reversing).  ``None`` means all commits.
    branch:
        Branch to analyse.  Falls back to the default HEAD if not found.
    show_progress:
        Whether to display a tqdm progress bar while extracting commits.

    Returns
    -------
    list[CommitRecord]
        Commits ordered oldest → newest.
    """
    local_path = Path(local_path)
    repo = _get_or_clone(repo_url, local_path)
    records = _extract_commits(repo, branch=branch, max_commits=max_commits, show_progress=show_progress)
    logger.info("Extracted %d commit records from %s", len(records), repo_url)
    return records


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_or_clone(repo_url: str, local_path: Path) -> Repo:
    """Return an existing Repo or clone a fresh one."""
    if local_path.exists():
        try:
            repo = Repo(local_path)
            logger.info("Found existing repo at %s — fetching latest …", local_path)
            origin = repo.remotes.origin
            origin.fetch()
            return repo
        except InvalidGitRepositoryError:
            logger.warning("%s exists but is not a git repo — removing and re-cloning.", local_path)
            import shutil
            shutil.rmtree(local_path)

    logger.info("Cloning %s → %s …", repo_url, local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    repo = Repo.clone_from(repo_url, local_path, depth=None)   # full history
    return repo


def _resolve_branch(repo: Repo, branch: str):
    """Return a commit reference for *branch*, falling back to HEAD."""
    try:
        return repo.commit(branch)
    except Exception:
        pass
    # Try common remote names
    for remote_ref in [f"origin/{branch}", f"refs/remotes/origin/{branch}"]:
        try:
            return repo.commit(remote_ref)
        except Exception:
            continue
    logger.warning("Branch '%s' not found — using HEAD.", branch)
    return repo.head.commit


def _extract_commits(
    repo: Repo,
    branch: str,
    max_commits: Optional[int],
    show_progress: bool,
) -> list[CommitRecord]:
    """Walk the commit graph and build CommitRecord objects."""
    start_commit = _resolve_branch(repo, branch)

    # Collect commits (most-recent first then reverse for chronological order)
    all_commits = list(repo.iter_commits(start_commit, max_count=max_commits))
    all_commits.reverse()  # oldest → newest

    records: list[CommitRecord] = []
    iterator = tqdm(all_commits, desc="Extracting commits", unit="commit", disable=not show_progress)

    for commit in iterator:
        record = _commit_to_record(commit)
        if record is not None:
            records.append(record)

    return records


def _commit_to_record(commit) -> Optional[CommitRecord]:
    """Convert a GitPython Commit object to a CommitRecord."""
    try:
        # File-level diff stats
        files_changed: list[str] = []
        lines_added = 0
        lines_removed = 0

        todo_added = 0
        todo_removed = 0

        if commit.parents:
            # Normal commit: diff against first parent
            parent = commit.parents[0]
            try:
                diffs = parent.diff(commit)
                for diff in diffs:
                    path = diff.b_path or diff.a_path
                    if path:
                        files_changed.append(path)
                    if diff.diff and len(diff.diff) < 100_000:
                        try:
                            for line in diff.diff.decode("utf-8", errors="replace").splitlines():
                                if line.startswith("+") and not line.startswith("+++"):
                                    todo_added += len(_TODO_RE.findall(line))
                                elif line.startswith("-") and not line.startswith("---"):
                                    todo_removed += len(_TODO_RE.findall(line))
                        except Exception:
                            pass

                # stats object is more reliable for line counts
                stats = commit.stats
                lines_added = stats.total.get("insertions", 0)
                lines_removed = stats.total.get("deletions", 0)
            except GitCommandError as exc:
                logger.debug("Diff error on %s: %s", commit.hexsha[:8], exc)
        else:
            # Root commit — treat all files as added
            try:
                for blob in commit.tree.traverse():
                    if hasattr(blob, "path"):
                        files_changed.append(blob.path)
                stats = commit.stats
                lines_added = stats.total.get("insertions", 0)
            except Exception as exc:
                logger.debug("Root commit traversal error on %s: %s", commit.hexsha[:8], exc)

        # Timestamps — GitPython exposes as UTC epoch integers
        authored_dt = datetime.fromtimestamp(commit.authored_date, tz=timezone.utc)
        committed_dt = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)

        return CommitRecord(
            sha=commit.hexsha,
            author_name=commit.author.name or "",
            author_email=commit.author.email or "",
            authored_date=authored_dt,
            committed_date=committed_dt,
            message=commit.message.strip(),
            files_changed=files_changed,
            lines_added=lines_added,
            lines_removed=lines_removed,
            todo_added=todo_added,
            todo_removed=todo_removed,
        )
    except Exception as exc:
        logger.warning("Skipping commit %s due to error: %s", getattr(commit, "hexsha", "?")[:8], exc)
        return None


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    from rich.console import Console
    from rich.table import Table

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    console = Console()

    REPO_URL = "https://github.com/django/django.git"
    LOCAL_PATH = Path("/tmp/django-debt-test")

    console.print(f"\n[bold cyan]Technical Debt Archaeologist — Ingestion Smoke Test[/bold cyan]")
    console.print(f"Target repo : [yellow]{REPO_URL}[/yellow]")
    console.print(f"Local cache : [yellow]{LOCAL_PATH}[/yellow]\n")

    records = ingest_repo(
        repo_url=REPO_URL,
        local_path=LOCAL_PATH,
        max_commits=200,    # keep the smoke-test fast
        branch="main",
    )

    # --- Summary table ---
    table = Table(title=f"Sample commits ({len(records)} total extracted)", show_lines=True)
    table.add_column("SHA", style="dim", width=10)
    table.add_column("Date", width=12)
    table.add_column("Author", width=22)
    table.add_column("+Lines", justify="right", style="green")
    table.add_column("-Lines", justify="right", style="red")
    table.add_column("Files", justify="right")
    table.add_column("Message (truncated)", width=45)

    for rec in records[-10:]:   # show 10 most-recent
        table.add_row(
            rec.sha[:8],
            rec.authored_date.strftime("%Y-%m-%d"),
            rec.author_name[:22],
            str(rec.lines_added),
            str(rec.lines_removed),
            str(len(rec.files_changed)),
            rec.message.splitlines()[0][:45],
        )

    console.print(table)

    # --- Aggregate stats ---
    total_churn = sum(r.churn for r in records)
    avg_files = sum(len(r.files_changed) for r in records) / max(len(records), 1)
    console.print(f"\n[bold]Aggregate stats[/bold]")
    console.print(f"  Commits analysed : {len(records)}")
    console.print(f"  Total churn (±)  : {total_churn:,} lines")
    console.print(f"  Avg files/commit : {avg_files:.1f}")
    console.print(f"  Date range       : {records[0].authored_date.date()} → {records[-1].authored_date.date()}")
    console.print("\n[green]✓ Ingestion layer OK[/green]\n")
