"""
Unit tests for all five history agents + synthesis.
No network calls, no LLM calls.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import make_commit
from models import CommitRecord


# ─── CommitQualityAgent ───────────────────────────────────────────────────────

class TestCommitQuality:
    def setup_method(self):
        from agents.commit_quality import CommitQualityAgent
        self.agent = CommitQualityAgent()

    def test_good_message_scores_high(self, good_commit):
        scores = self.agent.score_all([good_commit])
        assert len(scores) == 1
        assert scores[0].score >= 0.7

    def test_vague_message_scores_low(self, bad_commit):
        scores = self.agent.score_all([bad_commit])
        assert scores[0].score < 0.7

    def test_merge_commits_excluded(self):
        merge = make_commit(msg="Merge pull request #123 from user/branch")
        scores = self.agent.score_all([merge])
        assert len(scores) == 0

    def test_high_churn_penalised(self):
        big = make_commit(msg="refactor: restructure entire auth module", churn=1200)
        scores = self.agent.score_all([big])
        assert scores[0].score < 0.9

    def test_authored_date_populated(self, good_commit):
        scores = self.agent.score_all([good_commit])
        assert scores[0].authored_date is not None

    def test_empty_list_returns_empty(self):
        assert self.agent.score_all([]) == []


# ─── FileChurnAgent ───────────────────────────────────────────────────────────

class TestFileChurn:
    def setup_method(self):
        from agents.file_churn import FileChurnAgent
        self.agent = FileChurnAgent()

    def test_most_changed_file_ranks_first(self, commit_series):
        for c in commit_series:
            c.files_changed = ["hot/model.py", "cold/util.py"]
        # Make some commits only touch hot file
        for c in commit_series[:15]:
            c.files_changed = ["hot/model.py"]
        records = self.agent.analyse(commit_series, top_n=10)
        assert records[0].filepath == "hot/model.py"

    def test_top_n_respected(self, commit_series):
        for i, c in enumerate(commit_series):
            c.files_changed = [f"file_{i % 10}.py"]
        records = self.agent.analyse(commit_series, top_n=5)
        assert len(records) <= 5

    def test_churn_score_positive(self, commit_series):
        for c in commit_series:
            c.files_changed = ["src/main.py"]
        records = self.agent.analyse(commit_series)
        assert all(r.churn_score >= 0 for r in records)

    def test_empty_returns_empty(self):
        assert self.agent.analyse([]) == []


# ─── VelocityDeltaAgent ───────────────────────────────────────────────────────

class TestVelocityDelta:
    def setup_method(self):
        from agents.velocity_delta import VelocityDeltaAgent
        self.agent = VelocityDeltaAgent()

    def test_scores_normalised_0_to_1(self, commit_series):
        windows = self.agent.analyse(commit_series, window_days=14)
        assert all(0.0 <= w.velocity_score <= 1.0 for w in windows)

    def test_window_count_reasonable(self, commit_series):
        windows = self.agent.analyse(commit_series, window_days=14)
        assert len(windows) >= 2

    def test_out_of_order_commits_no_crash(self):
        commits = [
            make_commit(sha="a" * 40, days_offset=10),
            make_commit(sha="b" * 40, days_offset=0),
            make_commit(sha="c" * 40, days_offset=20),
        ]
        windows = self.agent.analyse(commits, window_days=7)
        assert len(windows) >= 1

    def test_single_commit_no_crash(self):
        windows = self.agent.analyse([make_commit()], window_days=14)
        assert len(windows) >= 1

    def test_empty_returns_empty(self):
        assert self.agent.analyse([]) == []


# ─── TodoDensityAgent ─────────────────────────────────────────────────────────

class TestTodoDensity:
    def setup_method(self):
        from agents.todo_density import TodoDensityAgent
        self.agent = TodoDensityAgent()

    def test_counts_added_todos(self, commit_series):
        for c in commit_series[:5]:
            c.todo_added = 3
        windows = self.agent.analyse(commit_series, window_days=14)
        total = sum(w.new_todos for w in windows)
        assert total == 15

    def test_resolved_todos_tracked(self, commit_series):
        for c in commit_series[:3]:
            c.todo_removed = 2
        windows = self.agent.analyse(commit_series, window_days=14)
        total_resolved = sum(w.resolved_todos for w in windows)
        assert total_resolved == 6

    def test_density_score_non_negative(self, commit_series):
        windows = self.agent.analyse(commit_series, window_days=14)
        assert all(w.density_score >= 0 for w in windows)

    def test_empty_returns_empty(self):
        assert self.agent.analyse([]) == []


# ─── PRPatternAgent ───────────────────────────────────────────────────────────

class TestPRPattern:
    def setup_method(self):
        from agents.pr_pattern import PRPatternAgent
        self.agent = PRPatternAgent()

    def test_detects_github_merge_commit(self):
        c = make_commit(msg="Merge pull request #42 from user/feature-branch")
        patterns = self.agent.analyse([c])
        assert len(patterns) == 1
        assert patterns[0].pr_number == 42
        assert patterns[0].is_merge_commit is True

    def test_detects_squash_merge(self):
        c = make_commit(msg="feat: add new endpoint (#99)")
        patterns = self.agent.analyse([c])
        assert len(patterns) == 1
        assert patterns[0].pr_number == 99

    def test_authored_date_populated(self):
        c = make_commit(msg="Merge pull request #7 from user/fix")
        patterns = self.agent.analyse([c])
        assert patterns[0].authored_date is not None

    def test_normal_commit_not_detected(self):
        c = make_commit(msg="feat: implement caching layer")
        patterns = self.agent.analyse([c])
        assert len(patterns) == 0

    def test_empty_returns_empty(self):
        assert self.agent.analyse([]) == []


# ─── Synthesis (heuristic path, no LLM) ──────────────────────────────────────

class TestSynthesis:
    def setup_method(self):
        from synthesis.synthesizer import SynthesisAgent
        self.agent = SynthesisAgent(openai_api_key="disabled")
        # Disable LLM by setting client to None
        self.agent._client = None

    def _run(self, n_commits=20):
        from agents.commit_quality import CommitQualityAgent
        from agents.file_churn import FileChurnAgent
        from agents.todo_density import TodoDensityAgent
        from agents.pr_pattern import PRPatternAgent
        from agents.velocity_delta import VelocityDeltaAgent

        commits = [
            make_commit(sha=f"{'d' * 38}{i:02d}", days_offset=i * 2, msg=f"feat: feature {i}")
            for i in range(n_commits)
        ]
        return self.agent.synthesize(
            repo_url="https://github.com/test/repo",
            repo_name="repo",
            quality_scores=CommitQualityAgent().score_all(commits),
            churn_records=FileChurnAgent().analyse(commits),
            todo_windows=TodoDensityAgent().analyse(commits),
            pr_patterns=PRPatternAgent().analyse(commits),
            velocity_windows=VelocityDeltaAgent().analyse(commits),
            commits=commits,
        )

    def test_result_has_events(self):
        result = self._run()
        assert len(result.debt_events) > 0

    def test_overall_score_in_range(self):
        result = self._run()
        assert 0.0 <= result.overall_debt_score <= 100.0

    def test_event_scores_in_range(self):
        result = self._run()
        for e in result.debt_events:
            assert 0.0 <= e.debt_score <= 100.0

    def test_severity_valid(self):
        from models import DebtSeverity
        result = self._run()
        valid = {s.value for s in DebtSeverity}
        for e in result.debt_events:
            assert e.severity.value in valid

    def test_author_records_populated(self):
        result = self._run()
        assert len(result.author_records) > 0

    def test_executive_summary_non_empty(self):
        result = self._run()
        assert len(result.executive_summary) > 10
