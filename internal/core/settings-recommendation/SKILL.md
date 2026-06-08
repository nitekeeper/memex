---
name: memex:core:settings-recommendation
description: On the first memex:run after a plugin version bump, offer (y/N, default No, once per version) to apply the cost-optimized recommended settings (model=sonnet, effortLevel=high, autoCompactEnabled=true) to ~/.claude/settings.json. Merge-safe and consent-gated. Python computes/applies; this procedure asks. Never touches managed-settings.json.
---

# memex:core:settings-recommendation

Consent surface for the settings-recommendation-on-upgrade feature. **Python
(`scripts/recommended_settings.py`) computes and applies; this procedure asks.**

This is a LOCAL CONFIG write. `~/.claude/settings.json` is a Claude Code config
file, NOT a Memex-managed store, so **M3 (all writes through the Librarian) does
NOT apply** — the write goes directly, never through the Librarian / Archivist /
Memex Core. The feature NEVER touches `managed-settings.json` and NEVER clobbers
existing settings keys (merge-safe: only the 3 recommended keys are written).

## When this runs

`skills/run/SKILL.md` Step 0.3 runs the read-only eligibility check after
bootstrap and BEFORE routing. It only reads this procedure when an offer is due
(plugin version bumped, not yet handled, recommended changes pending). If no
offer is due, Step 0.3 proceeds to routing silently — this procedure is never
read.

## Recipe

1. **Re-check eligibility (read-only).** Run:

   ```bash
   PYTHONPATH="<RESOLVED_PLUGIN_ROOT>" MEMEX_HOME="<RESOLVED_HOME>" python3 -c \
     'import json,sys; from scripts.recommended_settings import eligibility; e=eligibility(); print(json.dumps(e) if e else "")'
   ```

   If output is empty → STOP silently (no prompt, no write). Proceed to routing.

2. **Present the offer (default NO).** If eligible, display this block, substituting
   `<version>` from the eligibility result's `current_version`:

   ```text
   Memex was upgraded to v<version>. Apply cost-optimized recommended settings
   (model=sonnet, effortLevel=high, autoCompactEnabled=true) to ~/.claude/settings.json? (y/N)

   This is a merge: every existing settings key is preserved and only those 3
   keys are written. It never touches managed-settings.json. Default is No.
   ```

   End the turn. Wait for the user's reply. The default is **No** — an empty,
   ambiguous, or negative reply is treated as a decline.

   **Reply interpretation** (LLM-side):
   - **Affirmative** (`y`, `yes`, `yeah`, `yep`, `sure`, `ok`, `go ahead`, `do it`,
     `apply`): treat as YES.
   - **Anything else** (negative, empty, or ambiguous): treat as NO (default).

3. **On YES — apply, then record.** Run:

   ```bash
   PYTHONPATH="<RESOLVED_PLUGIN_ROOT>" MEMEX_HOME="<RESOLVED_HOME>" python3 -c \
     'import json; from scripts.recommended_settings import apply_recommended, write_state, current_plugin_version; \
      c=apply_recommended(); v=current_plugin_version(); write_state(v,"applied") if v else None; print(json.dumps(c))'
   ```

   Report the applied changes (the printed dict). Then proceed to routing.

4. **On NO — record the decline, then proceed.** Run:

   ```bash
   PYTHONPATH="<RESOLVED_PLUGIN_ROOT>" MEMEX_HOME="<RESOLVED_HOME>" python3 -c \
     'from scripts.recommended_settings import write_state, current_plugin_version; \
      v=current_plugin_version(); write_state(v,"declined") if v else None'
   ```

   Either way the version is now recorded, so the offer will NOT re-fire on the
   next `memex:run` for this version (consent-gated, once per version). Proceed
   to routing.

5. **Graceful no-op.** Any error in any step is a no-op — proceed to routing.
   The settings recommendation must never block or crash a memex invocation.
