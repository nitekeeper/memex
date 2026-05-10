import json
import pathlib
import subprocess
import sys

import frontmatter


def _git(args, cwd, check=True):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, check=check
    )


def _get_head_sha(project_root):
    return _git(["rev-parse", "HEAD"], cwd=project_root).stdout.strip()


def _validate_sha(project_root, sha):
    result = _git(["cat-file", "-t", sha], cwd=project_root, check=False)
    return result.returncode == 0


def _get_file_diff(project_root, sha, file_path):
    result = _git(
        ["diff", f"{sha}..HEAD", "--", file_path], cwd=project_root
    )
    return result.stdout


def _count_lines_changed(diff_text):
    added = sum(
        1 for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff_text.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )
    return added + removed


def run_sync(ai_dir):
    ai_path = pathlib.Path(ai_dir)
    if not ai_path.exists():
        print(f"Error: ai_dir not found: {ai_dir}", file=sys.stderr)
        sys.exit(1)

    project_root = str(ai_path.parent)

    try:
        head_sha = _get_head_sha(project_root)
    except subprocess.CalledProcessError as exc:
        print(f"Error: git unavailable or not a git repo: {exc}", file=sys.stderr)
        sys.exit(1)

    report = {"head": head_sha, "stale": [], "clean": [], "untracked": []}

    wiki_dir = ai_path / "wiki"
    if not wiki_dir.exists():
        print(json.dumps(report, indent=2))
        return

    for md_file in sorted(wiki_dir.glob("*.md")):
        post = frontmatter.load(str(md_file))
        meta = post.metadata
        page_id = str(meta.get("id", ""))
        title = str(meta.get("title", ""))
        page_path = str(md_file.relative_to(ai_path.parent)).replace("\\", "/")
        describes_files = list(meta.get("describes-files", []))
        synced_at_commit = meta.get("synced-at-commit")

        if not describes_files:
            report["untracked"].append(
                {"page": page_path, "id": page_id, "title": title}
            )
            continue

        if not synced_at_commit:
            report["stale"].append(
                {
                    "page": page_path,
                    "id": page_id,
                    "title": title,
                    "state": "NEVER_SYNCED",
                    "synced_at_commit": None,
                    "changed_files": [
                        {"path": fp.replace("\\", "/"), "diff": None, "lines_changed": None}
                        for fp in describes_files
                    ],
                }
            )
            continue

        if not _validate_sha(project_root, synced_at_commit):
            print(
                f"Error: synced-at-commit '{synced_at_commit}' in {md_file} "
                f"is not a valid git object",
                file=sys.stderr,
            )
            sys.exit(1)

        changed_files = []
        for fp in describes_files:
            diff_text = _get_file_diff(project_root, synced_at_commit, fp)
            if diff_text:
                changed_files.append(
                    {
                        "path": fp.replace("\\", "/"),
                        "diff": diff_text,
                        "lines_changed": _count_lines_changed(diff_text),
                    }
                )

        if changed_files:
            report["stale"].append(
                {
                    "page": page_path,
                    "id": page_id,
                    "title": title,
                    "state": "STALE",
                    "synced_at_commit": synced_at_commit,
                    "changed_files": changed_files,
                }
            )
        else:
            report["clean"].append(
                {
                    "page": page_path,
                    "id": page_id,
                    "title": title,
                    "state": "CLEAN",
                    "synced_at_commit": synced_at_commit,
                    "changed_files": [],
                }
            )

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect stale Memex wiki pages via git diff."
    )
    parser.add_argument("ai_dir", help="Path to the project's .ai/ directory")
    args = parser.parse_args()
    run_sync(args.ai_dir)
