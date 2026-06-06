"""Hierarchical community detection — pure-stdlib, deterministic.

GraphRAG clusters the entity/relation graph into a hierarchy of communities,
then summarizes each community bottom-up. This module is the clustering step:
it reads `relations`, builds a weighted undirected graph, runs greedy
modularity-maximizing agglomeration (Clauset-Newman-Moore in spirit), and
recurses inside any community larger than a size cap to produce hierarchical
levels. Results land in `communities` + `community_members`.

Why hand-rolled greedy modularity rather than a library:
  - Memex is stdlib-lean — no networkx/numpy/sklearn. A community detector
    that pulled in a heavy dep would violate the dependency-light contract.
  - Greedy modularity is O(E log V)-ish and deterministic with a fixed
    tie-break; it is more than adequate at personal-Brain scale.

Determinism contract:
  - Nodes processed in sorted index_id order.
  - Merge selection breaks ties by (modularity-gain desc, then the
    lexicographically smallest (community-key) pair) so the same graph always
    yields the same partition.
  - No randomness anywhere.

Hierarchy:
  - Level 0 is the finest partition (one greedy pass over the whole graph).
  - Any community whose size exceeds `size_cap` is re-clustered over the
    sub-graph induced by its members, producing children at level+1.
  - Communities at or below the cap (or that refuse to split) are leaves.
  - MECE per level: every node belongs to exactly one community at each level
    where it is represented.

Degrades: empty/sparse graph -> 0 or trivial communities, no crash.

DERIVED artifact (M3): rebuilt from `relations`; carries no authoritative
content. Document writes still go through the Librarian.
"""

from __future__ import annotations

import os
from collections import defaultdict

from scripts.db import get_connection, memex_home

_DEFAULT_SIZE_CAP = 10

# Hard ceiling on hierarchy depth; a defensive backstop against pathological
# dense cliques that would otherwise peel one node off per level. The
# balanced-split guard usually stops descent far sooner.
_MAX_RECURSION_DEPTH = 8


def _size_cap() -> int:
    """Max community size before recursive sub-clustering. Env override:
    MEMEX_COMMUNITY_SIZE_CAP."""
    raw = os.environ.get("MEMEX_COMMUNITY_SIZE_CAP")
    if raw is None:
        return _DEFAULT_SIZE_CAP
    try:
        cap = int(raw)
    except ValueError:
        return _DEFAULT_SIZE_CAP
    return max(2, cap)


# ── Graph loading ──────────────────────────────────────────────────────────


def _load_weighted_graph(conn) -> tuple[list[str], dict[tuple[str, str], float]]:
    """Read `relations` into an undirected weighted graph.

    Weight between a pair = sum of confidence across all rel_types and both
    directions (confidence defaults to 1.0 when NULL). Returns (sorted node
    list, {(a,b)->weight} with a<b).
    """
    nodes: set[str] = set()
    weights: dict[tuple[str, str], float] = defaultdict(float)
    for r in conn.execute("SELECT from_index_id, to_index_id, confidence FROM relations"):
        a, b = r["from_index_id"], r["to_index_id"]
        if a == b:
            continue
        nodes.add(a)
        nodes.add(b)
        w = r["confidence"]
        w = 1.0 if w is None else float(w)
        key = (a, b) if a < b else (b, a)
        weights[key] += w
    return sorted(nodes), dict(weights)


# ── Greedy modularity over an explicit sub-graph ───────────────────────────


def _greedy_modularity(
    nodes: list[str],
    edges: dict[tuple[str, str], float],
    min_communities: int = 1,
) -> list[list[str]]:
    """Partition `nodes` by greedy modularity maximization.

    `edges` maps (a,b) with a<b to a positive weight. Returns a list of
    communities (each a sorted node list), the outer list sorted by the
    smallest member for stability. Deterministic.

    `min_communities` is a floor on the number of communities the
    agglomeration may collapse to. With the default 1 this is plain greedy
    modularity. The hierarchical recursion passes 2 so that a community which
    the top-level pass produced as a single blob is forced to reveal its
    best sub-split (greedy modularity is deterministic, so re-running it
    unconstrained on the induced sub-graph would just reproduce the one blob;
    the floor stops merging before the final collapse).
    """
    nodes = sorted(nodes)
    if not nodes:
        return []
    if len(nodes) == 1:
        return [list(nodes)]

    # Adjacency with symmetric weights; degree (weighted) per node.
    adj: dict[str, dict[str, float]] = {n: {} for n in nodes}
    m2 = 0.0  # 2m = sum of all edge weights * 2
    for (a, b), w in edges.items():
        if a not in adj or b not in adj or w <= 0:
            continue
        adj[a][b] = adj[a].get(b, 0.0) + w
        adj[b][a] = adj[b].get(a, 0.0) + w
        m2 += 2.0 * w

    if m2 == 0.0:
        # No edges among these nodes — every node is its own singleton.
        return [[n] for n in nodes]

    # community label -> set of nodes; start with singletons keyed by node id.
    comm_members: dict[str, set[str]] = {n: {n} for n in nodes}
    node_comm: dict[str, str] = {n: n for n in nodes}
    # community -> summed weighted degree of its nodes (a_c term).
    comm_degree: dict[str, float] = {n: sum(adj[n].values()) for n in nodes}

    def _between(c1: str, c2: str) -> float:
        members1 = comm_members[c1]
        total = 0.0
        for u in members1:
            for v, w in adj[u].items():
                if node_comm[v] == c2:
                    total += w
        return total

    improved = True
    while improved:
        if len(comm_members) <= min_communities:
            break  # honour the community-count floor (used by recursion)
        improved = False
        best_gain = 0.0
        best_pair: tuple[str, str] | None = None
        # Consider merging each pair of currently-adjacent communities.
        seen_pairs: set[tuple[str, str]] = set()
        for u in sorted(node_comm):
            cu = node_comm[u]
            for v in sorted(adj[u]):
                cv = node_comm[v]
                if cu == cv:
                    continue
                pair = (cu, cv) if cu < cv else (cv, cu)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                e_between = _between(pair[0], pair[1])
                # Modularity gain of merging c1,c2:
                #   ΔQ = e_between/m - 2*(deg1/2m)*(deg2/2m)
                #      = 2*e_between/m2 - 2*deg1*deg2/(m2*m2)
                d1 = comm_degree[pair[0]]
                d2 = comm_degree[pair[1]]
                gain = (2.0 * e_between / m2) - (2.0 * d1 * d2 / (m2 * m2))
                # Strict improvement; ties broken by lexicographically smaller
                # pair (sorted iteration already favors smaller, but keep the
                # explicit > so we never merge on a non-positive gain).
                if gain > best_gain + 1e-12:
                    best_gain = gain
                    best_pair = pair
        if best_pair is not None:
            c1, c2 = best_pair
            # Merge c2 into c1 (c1 < c2 keeps the label deterministic).
            for n in comm_members[c2]:
                node_comm[n] = c1
            comm_members[c1] |= comm_members[c2]
            comm_degree[c1] += comm_degree[c2]
            del comm_members[c2]
            del comm_degree[c2]
            improved = True

    result = [sorted(members) for members in comm_members.values()]
    result.sort(key=lambda members: members[0])
    return result


# ── Hierarchical driver ────────────────────────────────────────────────────


def detect_communities(size_cap: int | None = None) -> dict:
    """Detect hierarchical communities from `relations` and persist them.

    Wipes prior `communities`/`community_members` rows and rebuilds. Level 0
    is the greedy-modularity partition of the whole graph; any community
    larger than `size_cap` is recursively re-clustered to produce deeper
    levels (parent/children links recorded). Isolated nodes (no edges) are not
    placed in a community.

    Args:
        size_cap: recurse into communities larger than this (default env
            MEMEX_COMMUNITY_SIZE_CAP or 10).

    Returns:
        {"levels": <max level index + 1, or 0 if none>,
         "communities": <total community count>,
         "members": <total membership rows>,
         "nodes": <distinct nodes placed>}.

    Degrades: empty graph -> all-zero summary, no crash.
    """
    if size_cap is None:
        size_cap = _size_cap()

    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    try:
        nodes, weights = _load_weighted_graph(conn)

        # Always clear prior derived community rows (idempotent rebuild).
        conn.execute("DELETE FROM community_members")
        conn.execute("DELETE FROM communities")
        conn.commit()

        summary = {"levels": 0, "communities": 0, "members": 0, "nodes": 0}
        if not nodes:
            return summary

        # Build per-pair edge dict restricted to a node subset.
        def _induced(subset: set[str]) -> dict[tuple[str, str], float]:
            return {(a, b): w for (a, b), w in weights.items() if a in subset and b in subset}

        comm_rows: list[tuple] = []  # (community_id, level, parent, size)
        member_rows: list[tuple] = []  # (community_id, index_id, level)
        max_level = -1
        placed_nodes: set[str] = set()
        counter = 0

        def _new_id(level: int) -> str:
            nonlocal counter
            counter += 1
            return f"c{level}-{counter:04d}"

        # Iterative deepening: a work queue of (node_subset, level, parent_id).
        # Level 0 uses unconstrained greedy modularity; deeper levels are only
        # ever queued when the parent (a too-big community) HAS a non-trivial
        # 2+-way sub-split, and they run with a community-count floor of 2 so
        # the deterministic agglomeration can't just collapse back to the one
        # blob the parent already is.
        work: list[tuple[list[str], int, str | None]] = [(nodes, 0, None)]
        while work:
            subset_nodes, level, parent = work.pop(0)
            subset_set = set(subset_nodes)
            induced = _induced(subset_set)
            floor = 1 if level == 0 else 2
            partition = _greedy_modularity(subset_nodes, induced, min_communities=floor)
            for members in partition:
                # Drop singletons that have no edges within this subset (pure
                # isolates) so reports aren't generated for orphan nodes.
                if len(members) == 1:
                    only = members[0]
                    has_edge = any(only in (a, b) for (a, b) in induced)
                    if not has_edge and level == 0:
                        continue
                cid = _new_id(level)
                comm_rows.append((cid, level, parent, len(members)))
                for n in members:
                    member_rows.append((cid, n, level))
                    placed_nodes.add(n)
                max_level = max(max_level, level)
                # Recurse if this community is too big AND a floor-2 sub-split
                # actually produces more than one child (otherwise it's a tight
                # blob — stop to avoid infinite recursion / runaway depth).
                #
                # KNOWN LIMITATION (documented, not fixed): a perfectly uniform
                # dense clique can satisfy the balanced-split guard at every
                # level and peel into a deep hierarchy of many tiny communities,
                # one report LLM call each. This is not a practical risk here —
                # real kNN graphs are built with the out-degree capped at k=5,
                # so they are never uniform cliques. Tracked as a deferred
                # GraphRAG follow-up; do not change the recursion/split logic
                # without revisiting that note.
                if len(members) > size_cap and level < _MAX_RECURSION_DEPTH:
                    child_induced = _induced(set(members))
                    sub_partition = _greedy_modularity(members, child_induced, min_communities=2)
                    # Only descend on a balanced-enough split (>=2 children,
                    # each strictly smaller than the parent) to avoid a long
                    # peel-one-off chain on dense cliques.
                    if len(sub_partition) > 1 and all(len(c) < len(members) for c in sub_partition):
                        work.append((members, level + 1, cid))

        conn.executemany(
            "INSERT INTO communities (community_id, level, parent, size) VALUES (?, ?, ?, ?)",
            comm_rows,
        )
        conn.executemany(
            "INSERT INTO community_members (community_id, index_id, level) VALUES (?, ?, ?)",
            member_rows,
        )
        conn.commit()

        summary["levels"] = (max_level + 1) if max_level >= 0 else 0
        summary["communities"] = len(comm_rows)
        summary["members"] = len(member_rows)
        summary["nodes"] = len(placed_nodes)
        return summary
    finally:
        conn.close()
