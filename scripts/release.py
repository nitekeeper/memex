"""Build a dist/v<version>/ bundle for Claude Code plugin distribution.

The bundle includes: .claude-plugin/ (the canonical manifest), scripts/,
skills/, internal/, db/, prompts/, a manifest.json with file inventory, and
INSTALL.md instructions.

dist/ body is gitignored; only manifest tracking is committed.
"""
from __future__ import annotations
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
import hashlib


# Claude Code reads .claude-plugin/plugin.json (the canonical manifest); the
# dist bundle MUST include that directory for `claude --plugin-dir` to work.
_INCLUDE_DIRS = [".claude-plugin", "scripts", "skills", "internal", "db", "prompts"]
_INCLUDE_FILES = ["pyproject.toml", "README.md", "USER_GUIDE.md", "CHANGELOG.md"]


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(version: str, target_root: Path | str = "dist") -> Path:
    """Build a dist bundle. Returns the path to the version directory."""
    target_root = Path(target_root)
    version_dir = target_root / f"v{version}"
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True)

    repo_root = Path.cwd()
    files_manifest: list[dict] = []

    # Copy directories
    for dirname in _INCLUDE_DIRS:
        src = repo_root / dirname
        if not src.exists():
            continue
        dst = version_dir / dirname
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for f in dst.rglob("*"):
            if f.is_file():
                files_manifest.append({
                    "path": str(f.relative_to(version_dir)),
                    "sha256": _hash_file(f),
                    "bytes": f.stat().st_size,
                })

    # Copy individual files
    for fname in _INCLUDE_FILES:
        src = repo_root / fname
        if not src.exists():
            continue
        dst = version_dir / fname
        shutil.copy2(src, dst)
        files_manifest.append({
            "path": fname,
            "sha256": _hash_file(dst),
            "bytes": dst.stat().st_size,
        })

    # INSTALL.md (generated, not copied)
    install_md = f"""# Memex v{version} Install Instructions

## Fresh install

1. Place this bundle in `~/.claude-code/plugins/memex/` (or your plugin directory).
2. Restart Claude Code or invoke `/plugin reload memex`.
3. Invoke `memex:run` and express your first intent (e.g. "ingest this article"). On first invocation of any Brain operation you will be prompted to register a human agent.

## Upgrading from v0.1

1. Set `MEMEX_V1_PATH` to your prior install root (the directory containing `.ai/`).
2. Place this bundle in `~/.claude-code/plugins/memex/` (replace prior bundle).
3. On first `memex:*` skill invocation, the plugin will archive v1's `.ai/` to
   `~/.memex/legacy/v1-wiki/` and bootstrap v2. v1 wiki content is preserved but
   NOT auto-migrated to v2 brain.db (per design decision).

## Verifying

Run `python -m scripts.install` to bootstrap `~/.memex/`. Then check:
- `~/.memex/agents.db` exists
- `~/.memex/index.db` exists
- `~/.memex/article.db` exists
- `~/.memex/registry.json` lists `agents`, `index`, `article`

## Embedding setup

v2.0 uses OpenAI text-embedding-3-small by default. Set `OPENAI_API_KEY`
or switch providers via `MEMEX_EMBEDDING_PROVIDER` (`voyage`, `local`).

## Skills shipped

**Memex v2.0 registers a single skill (`memex:run`)** with Claude Code,
then routes 24 internal procedures on demand via its body. This stays
well under Claude Code's 1% skill-description budget — the per-skill
descriptions for 24 entries would otherwise consume significant
context-window budget and risk truncation.

All 24 procedures live at `internal/<category>/<name>/SKILL.md` and are
reached via the routing tables inside `skills/run/SKILL.md`. The user
expresses intent (e.g. "ingest this article"); agents call CRUD
primitives by name. `memex:run` reads the matching procedure file on
demand and follows it.
"""
    (version_dir / "INSTALL.md").write_text(install_md)
    files_manifest.append({
        "path": "INSTALL.md",
        "sha256": _hash_file(version_dir / "INSTALL.md"),
        "bytes": (version_dir / "INSTALL.md").stat().st_size,
    })

    # Manifest
    manifest = {
        "version": version,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files_manifest),
        "files": sorted(files_manifest, key=lambda f: f["path"]),
    }
    (version_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return version_dir


if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "2.0.0"
    out = build(version)
    print(f"Built: {out}")
