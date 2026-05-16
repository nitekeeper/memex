"""One-command version bump.

Releases used to require touching plugin.json, pyproject.toml, README.md,
USER_GUIDE.md, tests/test_version.py, AND running scripts.release to swap
the dist/v*/manifest.json. After the version-drift cleanup, the only files
that hold the version are `.claude-plugin/plugin.json` and `pyproject.toml`,
with `dist/v<version>/manifest.json` built by `scripts.release`.

Usage:
    python -m scripts.bump 2.3.0

Steps:
  1. Validate the version string (PEP 440-ish: X.Y.Z, no leading 'v').
  2. Read the current version from plugin.json — refuse to downgrade or
     bump to the same value.
  3. Update plugin.json: `version` field + the inline 'Memex vX.Y.Z' token
     inside `description`.
  4. Update pyproject.toml: top-level `version` field.
  5. Remove the previous `dist/v<old>/manifest.json` (gitignored body, only
     manifest is tracked — see .gitignore).
  6. Call `scripts.release.build(new)` to produce `dist/v<new>/manifest.json`.

What this does NOT do (deliberate):
  - Write a CHANGELOG entry — that's editorial work, done by hand.
  - Commit, tag, or push — the release workflow triggers on tag push, but
    the tag itself is a human decision (see .github/workflows/release.yml).
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

from scripts import release


_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_version(s: str) -> tuple[int, int, int]:
    if not _VERSION_RE.match(s):
        raise ValueError(
            f"version must look like X.Y.Z (got {s!r}). "
            "Do not include a leading 'v'."
        )
    return tuple(int(p) for p in s.split("."))  # type: ignore[return-value]


def _read_plugin_json() -> dict:
    return json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))


def _write_plugin_json(data: dict) -> None:
    # Preserve trailing newline + 2-space indent (matches existing file)
    Path(".claude-plugin/plugin.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _update_plugin_json(new: str) -> str:
    data = _read_plugin_json()
    old = data["version"]
    data["version"] = new
    # description embeds 'Memex v<X.Y.Z> — ...' — swap any v<digit.digit.digit>
    data["description"] = re.sub(
        r"v\d+\.\d+\.\d+",
        f"v{new}",
        data["description"],
        count=1,
    )
    _write_plugin_json(data)
    return old


def _update_pyproject(new: str) -> str:
    path = Path("pyproject.toml")
    content = path.read_text(encoding="utf-8")
    match = re.search(r'^(version\s*=\s*")([^"]+)(")', content, re.MULTILINE)
    if not match:
        raise RuntimeError("pyproject.toml has no top-level version field")
    old = match.group(2)
    new_content = (
        content[: match.start(2)] + new + content[match.end(2) :]
    )
    path.write_text(new_content, encoding="utf-8")
    return old


def _remove_old_manifest(old: str) -> Path | None:
    p = Path("dist") / f"v{old}" / "manifest.json"
    if p.exists():
        p.unlink()
        # Also remove the empty version dir if it's now empty
        try:
            p.parent.rmdir()
        except OSError:
            pass
        return p
    return None


def bump(new: str) -> dict:
    """Bump the project to a new version. Returns a summary dict."""
    _parse_version(new)

    current = _read_plugin_json()["version"]
    if _parse_version(new) <= _parse_version(current):
        raise ValueError(
            f"refusing to bump to {new}: not greater than current {current}. "
            "scripts.bump only goes forward."
        )

    old_pj = _update_plugin_json(new)
    old_py = _update_pyproject(new)
    if old_pj != old_py:
        # Pre-existing drift — surface but don't fail; the bump still aligns them.
        print(
            f"warn: pre-bump drift detected (plugin.json was {old_pj}, "
            f"pyproject.toml was {old_py}); both now {new}"
        )

    removed = _remove_old_manifest(old_pj)
    built = release.build(new)

    return {
        "old": old_pj,
        "new": new,
        "removed_manifest": str(removed) if removed else None,
        "built_dist": str(built),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: python -m scripts.bump X.Y.Z (got {argv[1:]})", file=sys.stderr)
        return 2
    try:
        result = bump(argv[1])
    except (ValueError, RuntimeError) as e:
        print(f"bump failed: {e}", file=sys.stderr)
        return 1
    print(f"bumped {result['old']} -> {result['new']}")
    if result["removed_manifest"]:
        print(f"  removed: {result['removed_manifest']}")
    print(f"  built:   {result['built_dist']}")
    print()
    print("Next steps:")
    print(f"  1. Add a CHANGELOG.md entry for v{result['new']} (editorial — done by hand).")
    print( "  2. Commit the bump (plugin.json, pyproject.toml, CHANGELOG.md, dist/).")
    print(f"  3. After merge: git tag v{result['new']} && git push --tags")
    print( "     (the release workflow builds the GitHub Release from there).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
