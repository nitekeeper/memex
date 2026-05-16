from pathlib import Path

from scripts import brain, install
from scripts.db import get_connection, memex_home


def test_lint_returns_report_path(tmp_memex_home):
    install.run()
    report_path = brain.lint()
    assert Path(report_path).exists()


def test_lint_detects_brain_orphans(tmp_memex_home):
    install.run()
    # Create an index entry pointing to a nonexistent article row
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("idx-orphan", "x", "article", "article", "articles", "99999", "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()

    report_path = brain.lint()
    content = Path(report_path).read_text()
    assert "idx-orphan" in content
