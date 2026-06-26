"""Tests for the read-only Memex overview dashboard (scripts/dashboard.py).

Tier: the summary builder reads every registered store through
``require_bootstrap()``-guarded paths, so these use ``bootstrapped_home`` (full
install) — matching the M2 fixture-tier discipline. The HTTP handler is exercised
in-process against an ephemeral loopback port; no real browser is involved.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from scripts import dashboard


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_human_bytes():
    assert dashboard._human_bytes(0) == "0 B"
    assert dashboard._human_bytes(None) == "0 B"
    assert dashboard._human_bytes(512) == "512 B"
    assert dashboard._human_bytes(1024) == "1.0 KB"
    assert dashboard._human_bytes(5 * 1024 * 1024) == "5.0 MB"


def test_count_rejects_bad_identifier(tmp_store_path):
    con = sqlite3.connect(tmp_store_path)
    con.execute("CREATE TABLE t (id INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    ro = dashboard._ro_connect(tmp_store_path)
    try:
        assert dashboard._count(ro, "t") == 1
        # Injection-shaped identifier is rejected by safe_identifier → None.
        assert dashboard._count(ro, "t; DROP TABLE t") is None
        # Missing table degrades to None, never raises.
        assert dashboard._count(ro, "does_not_exist") is None
    finally:
        ro.close()


def test_ro_connect_missing_file(tmp_path):
    assert dashboard._ro_connect(tmp_path / "nope.db") is None


def test_ro_connect_is_read_only(tmp_store_path):
    sqlite3.connect(tmp_store_path).close()  # create empty db file
    ro = dashboard._ro_connect(tmp_store_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("CREATE TABLE x (id INTEGER)")
    finally:
        ro.close()


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------
def test_build_summary_structure(bootstrapped_home):
    s = dashboard.build_summary()
    for key in ("generated_at", "memex_home", "totals", "stores", "index", "brain", "agents"):
        assert key in s
    assert isinstance(s["stores"], list) and s["stores"]
    # Seeded internal agents present after install.
    assert s["totals"]["agents"] >= 5
    # The summary must be JSON-serializable (it is served as JSON).
    json.dumps(s, default=str)


def test_build_summary_reflects_inserted_rows(bootstrapped_home):
    from scripts import registry

    index_path = {r["name"]: r for r in registry.list_stores()}["index"]["path"]
    con = sqlite3.connect(index_path)
    con.execute(
        "INSERT INTO documents (index_id, domain, store, table_name, row_id, created_by) "
        "VALUES (?,?,?,?,?,?)",
        ("idx-test-1", "design", "article", "captures", "1", "tester"),
    )
    con.commit()
    con.close()

    s = dashboard.build_summary()
    assert s["totals"]["documents"] == 1
    assert s["index"]["documents_total"] == 1
    domains = {g["key"]: g["count"] for g in s["index"]["by_domain"]}
    assert domains.get("design") == 1


def test_build_summary_handles_missing_optional_store(bootstrapped_home):
    # code_graph.db is created by install; deleting it must not break the summary.
    (bootstrapped_home / "code_graph.db").unlink(missing_ok=True)
    s = dashboard.build_summary()
    assert s["code_graph"] is None
    assert s["totals"]["code_nodes"] == 0


def test_build_summary_requires_bootstrap(tmp_memex_home):
    from scripts.db import MemexNotInitializedError

    with pytest.raises(MemexNotInitializedError):
        dashboard.build_summary()


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------
def _run_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), dashboard._Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def test_handler_serves_html_json_and_health(bootstrapped_home):
    httpd = _run_server()
    port = httpd.server_address[1]
    try:
        status, ctype, body = _get(port, "/")
        assert status == 200
        assert "text/html" in ctype
        assert b"Memex" in body

        status, ctype, body = _get(port, "/api/summary")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert "totals" in data and "stores" in data

        status, _, body = _get(port, "/healthz")
        assert status == 200
        assert json.loads(body) == {"ok": True}
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_handler_sets_security_headers(bootstrapped_home):
    httpd = _run_server()
    port = httpd.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            assert r.headers.get("X-Content-Type-Options") == "nosniff"
            assert "default-src 'none'" in r.headers.get("Content-Security-Policy", "")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_handler_unknown_route_404(bootstrapped_home):
    httpd = _run_server()
    port = httpd.server_address[1]
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(port, "/secret/../etc")
        assert exc.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_handler_head_request(bootstrapped_home):
    httpd = _run_server()
    port = httpd.server_address[1]
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
            assert r.read() == b""  # HEAD must not return a body
            assert r.headers.get("Content-Length") == str(len(dashboard.INDEX_HTML.encode("utf-8")))
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_api_summary_returns_500_json_on_error(bootstrapped_home, monkeypatch):
    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(dashboard, "build_summary", boom)
    httpd = _run_server()
    port = httpd.server_address[1]
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(port, "/api/summary")
        err = exc.value
        assert err.code == 500
        assert "application/json" in err.headers.get("Content-Type", "")
        body = err.read()
        assert b"error" in body and b"kaboom" in body
        assert b"Traceback" not in body  # no stack trace leaked
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# Server construction: host guard + port scan (split into _make_server so the
# loopback boundary and the bind retry are testable without a blocking serve()).
# ---------------------------------------------------------------------------
def test_make_server_normalizes_empty_host_to_loopback():
    # "" would bind 0.0.0.0 (all interfaces); it must be normalized to loopback
    # and must NOT slip past the --allow-non-local guard.
    httpd = dashboard._make_server("", 0, allow_non_local=False)
    try:
        assert httpd.server_address[0] == "127.0.0.1"
    finally:
        httpd.server_close()


def test_make_server_refuses_non_local_without_flag():
    with pytest.raises(SystemExit):
        dashboard._make_server("8.8.8.8", 0, allow_non_local=False)


def test_make_server_port_scan_skips_busy_port():
    import socket

    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind(("127.0.0.1", 0))
    busy_port = occupied.getsockname()[1]
    occupied.listen(1)
    try:
        httpd = dashboard._make_server("127.0.0.1", busy_port, bind_retries=10)
        try:
            assert httpd.server_address[1] != busy_port
            assert busy_port < httpd.server_address[1] <= busy_port + 9
        finally:
            httpd.server_close()
    finally:
        occupied.close()


def test_make_server_raises_when_scan_range_exhausted():
    import socket

    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind(("127.0.0.1", 0))
    busy_port = occupied.getsockname()[1]
    occupied.listen(1)
    try:
        with pytest.raises(SystemExit):
            dashboard._make_server("127.0.0.1", busy_port, bind_retries=1)
    finally:
        occupied.close()


def test_display_url_brackets_ipv6():
    assert dashboard._display_url("127.0.0.1", 8765) == "http://127.0.0.1:8765/"
    assert dashboard._display_url("::1", 8765) == "http://[::1]:8765/"
    assert dashboard._display_url("", 8765) == "http://127.0.0.1:8765/"


def test_main_once_prints_json(bootstrapped_home, capsys):
    rc = dashboard.main(["--once"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "totals" in out and "stores" in out


def test_build_summary_survives_corrupt_store(bootstrapped_home):
    # A present-but-corrupt registered store must degrade, not abort the summary.
    from scripts import registry

    article = {r["name"]: r for r in registry.list_stores()}["article"]["path"]
    with open(article, "wb") as fh:
        fh.write(b"this is not a sqlite database at all")
    s = dashboard.build_summary()  # must not raise
    by_name = {x["name"]: x for x in s["stores"]}
    assert by_name["article"]["tables"] == []
    assert by_name["article"]["total_rows"] == 0
