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
# build_graph — the 3D knowledge-graph projection
# ---------------------------------------------------------------------------
def _index_conn(bootstrapped_home):
    from scripts import registry

    path = {r["name"]: r for r in registry.list_stores()}["index"]["path"]
    return sqlite3.connect(path)  # plain connect: FK off, so we can seed dangling rows


def _insert_doc(con, index_id, *, domain="design", key=None, metadata=None):
    con.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, metadata, created_by) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (index_id, key, domain, "article", "captures", index_id, metadata, "tester"),
    )


def test_node_label_prefers_key_then_metadata_then_domain():
    assert (
        dashboard._node_label(
            {"key": "my-key", "metadata": None, "domain": "d", "table_name": "t", "row_id": "1"}
        )
        == "my-key"
    )
    assert (
        dashboard._node_label(
            {
                "key": None,
                "metadata": '{"title": "Hello"}',
                "domain": "d",
                "table_name": "t",
                "row_id": "1",
            }
        )
        == "Hello"
    )
    assert (
        dashboard._node_label(
            {"key": None, "metadata": "not json", "domain": "dom", "table_name": "t", "row_id": "9"}
        )
        == "dom:9"
    )
    assert (
        dashboard._node_label(
            {"key": None, "metadata": None, "domain": None, "table_name": None, "row_id": "9"}
        )
        == "node:9"
    )


def test_build_graph_empty_index(bootstrapped_home):
    g = dashboard.build_graph()
    assert g == {"nodes": [], "links": [], "truncated": False}


def test_build_graph_reflects_docs_and_relations(bootstrapped_home):
    con = _index_conn(bootstrapped_home)
    _insert_doc(con, "a", domain="design", key="Node A")
    _insert_doc(con, "b", domain="meeting")
    con.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type, confidence) VALUES (?,?,?,?)",
        ("a", "b", "cites", 0.9),
    )
    con.commit()
    con.close()
    g = dashboard.build_graph()
    assert len(g["nodes"]) == 2
    assert len(g["links"]) == 1
    link = g["links"][0]
    assert link["source"] == "a" and link["target"] == "b" and link["type"] == "cites"
    labels = {n["label"] for n in g["nodes"]}
    assert "Node A" in labels


def test_build_graph_drops_dangling_and_self_links(bootstrapped_home):
    con = _index_conn(bootstrapped_home)
    _insert_doc(con, "x")
    con.executemany(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?,?,?)",
        [("x", "ghost", "cites"), ("x", "x", "relates")],  # dangling endpoint + self-loop
    )
    con.commit()
    con.close()
    g = dashboard.build_graph()
    assert len(g["nodes"]) == 1
    assert g["links"] == []  # both excluded


def test_build_graph_truncates(bootstrapped_home):
    con = _index_conn(bootstrapped_home)
    for i in range(3):
        _insert_doc(con, f"n{i}")
    con.commit()
    con.close()
    g = dashboard.build_graph(max_nodes=2)
    assert len(g["nodes"]) == 2
    assert g["truncated"] is True


def test_build_graph_colors_by_community(bootstrapped_home):
    con = _index_conn(bootstrapped_home)
    _insert_doc(con, "c1")
    con.execute(
        "INSERT INTO community_members (community_id, index_id, level) VALUES (?,?,?)",
        ("comm-7", "c1", 0),
    )
    con.commit()
    con.close()
    g = dashboard.build_graph()
    assert g["nodes"][0]["community"] == "comm-7"


def test_build_graph_survives_corrupt_index(bootstrapped_home):
    from scripts import registry

    path = {r["name"]: r for r in registry.list_stores()}["index"]["path"]
    with open(path, "wb") as fh:
        fh.write(b"definitely not a sqlite database")
    g = dashboard.build_graph()  # must not raise
    assert g["nodes"] == [] and g["links"] == []


def test_build_graph_truncation_boundary_exact(bootstrapped_home):
    # Exactly max_nodes documents must NOT be flagged truncated (guards > vs >=).
    con = _index_conn(bootstrapped_home)
    for i in range(2):
        _insert_doc(con, f"e{i}")
    con.commit()
    con.close()
    g = dashboard.build_graph(max_nodes=2)
    assert len(g["nodes"]) == 2
    assert g["truncated"] is False


def test_node_label_non_dict_json_falls_back():
    # Valid JSON that is not an object → fall through to domain:row_id.
    for md in ("[1,2,3]", '"a string"', "null", "42"):
        assert (
            dashboard._node_label(
                {"key": None, "metadata": md, "domain": "dom", "table_name": "t", "row_id": "7"}
            )
            == "dom:7"
        )
    # name / topic are accepted alongside title.
    assert (
        dashboard._node_label(
            {
                "key": None,
                "metadata": '{"name": "N"}',
                "domain": "d",
                "table_name": "t",
                "row_id": "1",
            }
        )
        == "N"
    )
    assert (
        dashboard._node_label(
            {
                "key": None,
                "metadata": '{"topic": "T"}',
                "domain": "d",
                "table_name": "t",
                "row_id": "1",
            }
        )
        == "T"
    )


def test_build_graph_requires_bootstrap(tmp_memex_home):
    from scripts.db import MemexNotInitializedError

    with pytest.raises(MemexNotInitializedError):
        dashboard.build_graph()


def test_graph_html_renders_data_as_data_not_html():
    """Static data/instruction-boundary guard over the viewer: DB-derived
    strings must reach canvas/DOM as data (fillText/textContent), and the only
    innerHTML writes must be empty-string clears — never data concatenation."""
    html = dashboard.GRAPH_HTML
    assert "ctx.fillText(a.label" in html  # node labels drawn as canvas text
    assert ".textContent" in html  # tooltip / legend / stats set as text
    # Every innerHTML assignment is the empty clear — no data is ever injected.
    assert html.count("innerHTML") == html.count('innerHTML = ""')
    assert "insertAdjacentHTML" not in html
    assert "outerHTML" not in html


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


def test_handler_serves_graph_page_and_api(bootstrapped_home):
    httpd = _run_server()
    port = httpd.server_address[1]
    try:
        status, ctype, body = _get(port, "/graph")
        assert status == 200
        assert "text/html" in ctype
        assert b"Knowledge graph" in body

        status, ctype, body = _get(port, "/api/graph")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert set(data) >= {"nodes", "links", "truncated"}
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
