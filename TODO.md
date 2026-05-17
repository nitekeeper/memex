# TODO

Deferred work tracked here so it survives session boundaries. Cross out items as they land or get explicitly dropped.

## When this repo goes public

GitHub Pro features (branch protection, auto-merge, CodeQL) become free on public repos. Wire them up the moment the visibility flips:

- [ ] **Enable branch protection on `main`** so the CI gates we ship actually block merges:
  ```bash
  gh api -X PUT repos/nitekeeper/memex/branches/main/protection \
    -F 'required_status_checks[strict]=true' \
    -F 'required_status_checks[contexts][]=lint' \
    -F 'required_status_checks[contexts][]=security' \
    -F 'required_status_checks[contexts][]=tests' \
    -F enforce_admins=false \
    -F required_pull_request_reviews= \
    -F restrictions=
  ```
  Today the workflows report pass/fail visually but a maintainer can merge red PRs. Branch protection is the actual rejection mechanism.

- [ ] **Enable `allow_auto_merge` on the repo** so future Dependabot and release PRs can self-merge after CI passes:
  ```bash
  gh api -X PATCH repos/nitekeeper/memex -F allow_auto_merge=true
  ```
  Today the API silently no-ops because the private-repo plan blocks it.

- [ ] **Enable CodeQL.** GitHub-hosted semantic analysis; free for public repos, paid (GitHub Advanced Security) for private. Adds another layer of static analysis beyond Ruff and Bandit.

- [ ] (Optional) **Connect SonarCloud.** Same calculus — free for public, paid for private. Useful if you want code-smell dashboards and inline PR comments beyond what CodeQL provides.

## Release-workflow polish

- [ ] **Make `release.yml`'s `Create GitHub Release` step idempotent.** Today, if a release-workflow run fails after creating the release and you re-run failed jobs, the second `gh release create` errors with "a release with the same tag name already exists." Either add `--clobber`, or pre-check with `gh release view "v$TAG"` and only create if absent. Low priority — only matters on failed reruns.

## Token hygiene

- [ ] **Confirm `AGORA_DISPATCH_TOKEN` expiry is set** (should be 1 year per the setup walkthrough). If not, rotate.

## Cross-project parity

- [ ] **Atelier symmetry.** Atelier currently has none of the gatekeepers / release-workflow / push-loop wiring we set up on memex and agora. When it's worth the time, replicate the memex pattern there: pyproject Ruff + Bandit config, CI workflow, Dependabot, scripts/bump (if atelier ships releases), AGORA_DISPATCH_TOKEN secret, release workflow that dispatches to agora.
