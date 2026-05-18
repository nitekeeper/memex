"""Plugin-anchored path constants resolve regardless of CWD."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


def test_imports_succeed():
    from scripts.paths import DB_DIR, PLUGIN_ROOT, PROMPTS_DIR

    assert PLUGIN_ROOT.is_absolute()
    assert DB_DIR.is_dir()
    assert PROMPTS_DIR.is_dir()


def test_plugin_root_contains_expected_dirs():
    from scripts.paths import PLUGIN_ROOT

    assert (PLUGIN_ROOT / "scripts").is_dir()
    assert (PLUGIN_ROOT / "db").is_dir()
    assert (PLUGIN_ROOT / "prompts").is_dir()


def test_db_dir_contains_sql_files():
    from scripts.paths import DB_DIR

    for fname in ("agents.sql", "index.sql", "brain.sql", "migrations_table.sql"):
        assert (DB_DIR / fname).is_file(), f"missing {fname}"


def test_prompts_dir_contains_md_files():
    from scripts.paths import PROMPTS_DIR

    for fname in ("librarian.md", "reference_librarian.md", "synthesizer.md"):
        assert (PROMPTS_DIR / fname).is_file(), f"missing {fname}"


def test_paths_cwd_independent(tmp_path):
    """Subprocess from foreign CWD resolves to the same PLUGIN_ROOT."""
    from scripts.paths import PLUGIN_ROOT as EXPECTED

    result = (
        subprocess.check_output(
            [sys.executable, "-c", "from scripts.paths import PLUGIN_ROOT; print(PLUGIN_ROOT)"],
            cwd=str(tmp_path),
            env={**os.environ, "PYTHONPATH": str(EXPECTED)},
        )
        .decode()
        .strip()
    )
    assert Path(result) == EXPECTED


def _ast_has_relative_path_literal(src: str, prefix: str) -> bool:
    """True if source has any Call(...string-starts-with(prefix))."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and node.args:
            arg = node.args[0]
            if (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.startswith(prefix)
            ):
                return True
    return False
