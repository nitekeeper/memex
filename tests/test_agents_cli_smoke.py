"""Regression: `python -m scripts.agents` must stay reachable as a CLI.

scripts/agents was refactored from a single module (scripts/agents.py) into a
package (scripts/agents/__init__.py). A package needs a __main__.py for
`python -m scripts.agents` to dispatch; without it the invocation dies with
"No module named scripts.agents.__main__" and the breakage is silent because
nothing exercised the CLI entry point.

These tests run the entry point as a subprocess (mirroring
test_paths.py::test_paths_cwd_independent) so a future re-break fails loudly.
$MEMEX_HOME is pointed at an isolated tmp dir so the test never touches the
host's real ~/.memex/.
"""

from __future__ import annotations

import os
import subprocess
import sys

from scripts.paths import PLUGIN_ROOT


def _run(args, tmp_path):
    env = {
        **os.environ,
        "PYTHONPATH": str(PLUGIN_ROOT),
        "MEMEX_HOME": str(tmp_path / "memex_home"),
        "MEMEX_HOME_ALLOW_UNUSUAL": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "scripts.agents", *args],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_module_help_dispatches(tmp_path):
    """`python -m scripts.agents --help` must dispatch and exit 0."""
    result = _run(["--help"], tmp_path)
    assert result.returncode == 0, (
        f"`python -m scripts.agents --help` exited {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "usage: python -m scripts.agents" in result.stdout


def test_module_no_command_is_usage_error(tmp_path):
    """Bare `python -m scripts.agents` (no subcommand) prints usage and exits 1."""
    result = _run([], tmp_path)
    assert result.returncode == 1, (
        f"bare invocation exited {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "usage: python -m scripts.agents" in result.stdout
