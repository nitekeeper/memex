"""install.run() succeeds regardless of CWD; ignores shadowing db/ in CWD.

v2.5.0 §B: bundle file reads (agents.sql, *.sql, prompts/) anchor to
PLUGIN_ROOT (scripts.paths) so the installer behaves the same whether
invoked from the plugin tree or from an unrelated working directory.
"""

from __future__ import annotations

import io
import sqlite3
import sys


def test_install_runs_from_alt_cwd(tmp_memex_home, tmp_path, monkeypatch):
    alt = tmp_path / "elsewhere"
    alt.mkdir()
    monkeypatch.chdir(alt)
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))

    from scripts import install

    install.run()

    for f in ("registry.json", "agents.db", "index.db", "article.db"):
        assert (tmp_memex_home / f).exists(), f"{f} missing after install from alt CWD"


def test_install_idempotent(tmp_memex_home, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\ny\n"))

    from scripts import install

    install.run()
    install.run()

    assert (tmp_memex_home / "registry.json").exists()


def test_install_ignores_shadowing_db_dir(tmp_memex_home, tmp_path, monkeypatch):
    fake_db = tmp_path / "db"
    fake_db.mkdir()
    (fake_db / "agents.sql").write_text("CREATE TABLE bogus (x INTEGER);")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))

    from scripts import install

    install.run()

    conn = sqlite3.connect(str(tmp_memex_home / "agents.db"))
    try:
        agents_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        ).fetchone()
        bogus_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bogus'"
        ).fetchone()
    finally:
        conn.close()

    assert agents_row is not None, "real agents table missing — installer read shadowed db/"
    assert bogus_row is None, "shadowing db/agents.sql in CWD was sourced"
