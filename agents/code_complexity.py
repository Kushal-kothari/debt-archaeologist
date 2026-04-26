"""
agents/code_complexity.py

AST-level code complexity analysis on the current HEAD snapshot.

Metrics per Python file:
  - Cyclomatic complexity (McCabe) per function
  - Maximum nesting depth
  - Import coupling (number of imports)
  - Average / max function length
  - List of complex functions (CC > 10)

Composite complexity_score (0-1, higher = worse):
  0.4 * avg_cc/15  +  0.3 * max_cc/30  +  0.2 * nesting/8  +  0.1 * imports/30
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Optional

try:
    from models import CodeComplexityRecord
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import CodeComplexityRecord

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    "migrations", ".tox", "build", "dist", ".eggs", "htmlcov", ".mypy_cache",
    "site-packages", ".pytest_cache",
}
_SKIP_STEMS = {"test_", "_test", "conftest", "setup", "manage"}


def _skip(path: Path) -> bool:
    if any(part in _SKIP_DIRS for part in path.parts):
        return True
    stem = path.stem.lower()
    return any(stem.startswith(p) or stem.endswith(p.lstrip("_")) for p in _SKIP_STEMS)


def _cyclomatic_complexity(func: ast.AST) -> int:
    """McCabe CC = 1 + number of decision points."""
    cc = 1
    for node in ast.walk(func):
        if isinstance(node, (
            ast.If, ast.While, ast.For, ast.AsyncFor,
            ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Assert,
        )):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            cc += len(node.values) - 1
        elif isinstance(node, ast.comprehension) and node.ifs:
            cc += len(node.ifs)
    return cc


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    control = (ast.If, ast.For, ast.While, ast.With, ast.Try,
               ast.AsyncFor, ast.AsyncWith)
    mx = depth
    for child in ast.iter_child_nodes(node):
        d = _max_nesting(child, depth + 1 if isinstance(child, control) else depth)
        mx = max(mx, d)
    return mx


class CodeComplexityAgent:
    """Stateless agent — call analyse(repo_path) on the cloned repo root."""

    def analyse(self, repo_path: Path, max_files: int = 150) -> list[CodeComplexityRecord]:
        py_files = [f for f in repo_path.rglob("*.py") if not _skip(f)][:max_files]
        records = []
        for fp in py_files:
            rec = self._analyse_file(fp, repo_path)
            if rec:
                records.append(rec)
        return sorted(records, key=lambda r: r.complexity_score, reverse=True)

    def _analyse_file(self, filepath: Path, root: Path) -> Optional[CodeComplexityRecord]:
        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
            if len(source) > 300_000:
                return None

            tree = ast.parse(source, filename=str(filepath))

            funcs = [
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if not funcs:
                return None

            complexities = [_cyclomatic_complexity(f) for f in funcs]
            lengths = [
                f.end_lineno - f.lineno + 1
                for f in funcs if hasattr(f, "end_lineno") and f.end_lineno
            ]
            imports = sum(
                1 for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom))
            )
            nesting = _max_nesting(tree)

            avg_cc  = sum(complexities) / len(complexities)
            max_cc  = max(complexities)
            avg_len = sum(lengths) / len(lengths) if lengths else 0
            complex_fns = [f.name for f, cc in zip(funcs, complexities) if cc > 10][:5]

            score = min(1.0, round(
                (avg_cc / 15.0) * 0.4
                + (max_cc / 30.0) * 0.3
                + (min(nesting, 8) / 8.0) * 0.2
                + (min(imports, 30) / 30.0) * 0.1,
                3,
            ))

            rel = str(filepath.relative_to(root)).replace("\\", "/")
            return CodeComplexityRecord(
                filepath=rel,
                language="python",
                avg_cyclomatic_complexity=round(avg_cc, 2),
                max_cyclomatic_complexity=max_cc,
                avg_function_length=round(avg_len, 1),
                num_functions=len(funcs),
                import_count=imports,
                max_nesting_depth=nesting,
                complex_functions=complex_fns,
                complexity_score=score,
            )
        except (SyntaxError, RecursionError):
            return None
        except Exception as exc:
            logger.debug("Skipping %s: %s", filepath.name, exc)
            return None
