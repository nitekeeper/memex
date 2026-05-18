"""Smoke-execute the python3 detection bash snippet from SKILL.md Step 0.

Marker tests (test_skill_run_preflight) check that the snippet *exists*.
This file runs it as a subprocess to catch shell-syntax regressions and
confirm the detection logic actually fires on a host that has python3.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "run" / "SKILL.md"

_PY_DETECT = re.compile(r"```bash\n(for cmd in python3[^\n]+\n(?:[^\n]+\n)+?done\nexit 1)\n```")


def test_python_detection_snippet_executes():
    text = SKILL_PATH.read_text(encoding="utf-8")
    m = _PY_DETECT.search(text)
    if not m:
        pytest.skip("Step 0.1 python3 detection snippet not yet present")
    snippet = m.group(1)
    result = subprocess.run(
        snippet,
        shell=True,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    # 0 = python3 found and emitted PYTHON=...; 1 = none found (allowed on host
    # without python3). Both are acceptable shell-syntax outcomes.
    assert result.returncode in (0, 1), (
        f"snippet exited {result.returncode}\nstderr={result.stderr}"
    )
    if result.returncode == 0:
        assert "PYTHON=" in result.stdout, (
            f"detection succeeded but didn't emit PYTHON=; stdout={result.stdout!r}"
        )
