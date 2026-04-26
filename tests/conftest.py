"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from models import CommitRecord


def _dt(days_offset: int = 0) -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc) + timedelta(days=days_offset)


def make_commit(
    sha: str = "a" * 40,
    msg: str = "feat: implement user authentication with JWT",
    churn: int = 80,
    files: list[str] | None = None,
    todo_added: int = 0,
    todo_removed: int = 0,
    days_offset: int = 0,
    author: str = "alice@example.com",
) -> CommitRecord:
    dt = _dt(days_offset)
    return CommitRecord(
        sha=sha,
        author_name="Alice",
        author_email=author,
        authored_date=dt,
        committed_date=dt,
        message=msg,
        files_changed=files or ["src/app.py"],
        lines_added=churn // 2,
        lines_removed=churn // 2,
        todo_added=todo_added,
        todo_removed=todo_removed,
    )


@pytest.fixture
def good_commit():
    return make_commit(msg="feat: add OAuth2 provider integration with refresh token support")


@pytest.fixture
def bad_commit():
    return make_commit(msg="fix", sha="b" * 40)


@pytest.fixture
def commit_series():
    """20 commits spread over 60 days."""
    return [
        make_commit(sha=f"{'c' * 38}{i:02d}", days_offset=i * 3, msg=f"feat: feature {i}")
        for i in range(20)
    ]
