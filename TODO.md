# TODO

Deferred work tracked here so it survives session boundaries. Cross out items as they land or get explicitly dropped.

## Post-public unlocks

Memex is public; branch protection on `main` is enabled (1 required review + the three CI status checks). Remaining:

- [ ] **Enable CodeQL.** GitHub-hosted semantic analysis; free for public repos, paid (GitHub Advanced Security) for private. Adds another layer of static analysis beyond Ruff and Bandit. — currently `not-configured`.

## Release-workflow polish

- [ ] **Make `release.yml`'s `Create GitHub Release` step idempotent.** Today, if a release-workflow run fails after creating the release and you re-run failed jobs, the second `gh release create` errors with "a release with the same tag name already exists." Either add `--clobber`, or pre-check with `gh release view "v$TAG"` and only create if absent. Low priority — only matters on failed reruns.
