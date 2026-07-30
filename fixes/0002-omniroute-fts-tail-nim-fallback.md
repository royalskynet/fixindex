---
id: 0002
slug: omniroute-fts-tail-nim-fallback
title: OmniRoute FTS combo tail NIM fallback
tags: [omniroute, fts, combo, nvidia-nim, launchd, timeout, readiness]
symptoms:
  - "dead placeholder wrapper scripts"
  - "rebuild-combos.py only rebuilds 2 combos not 5"
  - "dirty changes after live DB edit"
  - "repo config JSON out of sync with live SQLite combo"
  - "FTS OmniRoute combo needs another NIM after OpenRouter free"
  - "free-tools-heavy OpenRouter free tail fallback should continue to pinned NIM"
  - "add NVIDIA NIM key as final fallback in free-tools-heavy"
  - "Stream produced no non-ping SSE event within 60000ms"
  - "504 POST /v1/responses Total In 0 Total Out 0"
  - "strip-proxy 200 but Codex gets 502"
  - "omniroute 20128 connection refused / 000"
  - "launchctl print Could not find service 501"
  - "plist env change not taking effect after kickstart"
  - "deepseek-v4-pro slow prefill stall fallback"
  - "slow prefill ping-only timeout readiness"
  - "502 upstream dead orphan process"
  - "kickstart only restarts process does not re-read plist"
  - "launchd bootstrap kickstart plist env diff"
  - "plist env fix reverted after install-launchd.sh re-run"
  - "STREAM_READINESS_MAX_TIMEOUT_MS reset to default"
  - "live fix not synced to plist template"
status: active
supersedes: []
related: []
---
# 0002 omniroute-fts-tail-nim-fallback

## §1 Add a pinned NIM fallback after OpenRouter free in FTS combo
**Symptom:** User asks to add another NVIDIA NIM key after the OpenRouter free entry at the end of the OmniRoute combo currently used by FTS.
**Root cause:** FTS uses Codex config model `free-tools-heavy` through OmniRoute, and OmniRoute's live routing source is `~/.omniroute/storage.sqlite`; editing repo JSON alone can leave the running combo unchanged. Combo steps support `connectionId`, so a tail NIM fallback can be pinned to the newly added key instead of being mixed into the whole `nvidia` provider pool.
**Fix:** Back up `~/.omniroute/storage.sqlite*`; add the secret only to local credentials (`~/.creds/nvidia/.env`, e.g. `NVIDIA_API_KEY_2=...`); add a matching `provider_connections` row with encrypted `api_key`; append `{ "model": "nvidia/deepseek-ai/deepseek-v4-pro", "providerId": "nvidia", "connectionId": "<new-connection-id>" }` after `openrouter/openrouter/free` in `free-tools-heavy`; keep `config/providers.json`, `config/combo-free-tools-heavy.json`, `config/model-mappings.json`, and the live SQLite row in sync; restart `com.royalskynet.freetools-omniroute` and `com.royalskynet.freetools-stripproxy`.
**Verify:** `sqlite3 ~/.omniroute/storage.sqlite` should show `free-tools-heavy` model count increased by one, the second-last model as `openrouter/openrouter/free`, the last model as `nvidia/deepseek-ai/deepseek-v4-pro`, and the last step's `connectionId` equal to the new NVIDIA connection. The new provider row should be active and `api_key` should start with `enc:v1:`. Direct NVIDIA chat probe should return `OK`; strip-proxy `/v1/models` should respond after restart.
**Retrospective:** Previous OmniRoute fixes already showed JSON and live SQLite can diverge. Treat combo changes as two surfaces: repo config for reproducibility, live SQLite for actual routing.

## §2 Config JSON + rebuild script + dead wrappers not synced with live SQLite combo changes
**Symptom:** After editing combo in live SQLite (`30274`), the repo config files (`config/combo-free-tools-heavy.json`, `config/providers.json`, `config/model-mappings.json`) stayed out of sync. `scripts/rebuild-combos.py` only rebuilt 2 of 5 combos. Two dead wrapper scripts (`scripts/claude-free-tools`, `scripts/happy-free-tools`) contained only placeholder keys and had zero references. All accumulated as uncommitted dirty changes documented in `docs/remaining-dirty-changes.md`.
**Root cause:** Previous live SQLite combo edits were applied via inline Python script (`30274`) without also syncing the source-of-truth JSON configs. The rebuild script's combo list was hard-coded to two names.
**Fix:** Commit all six dirty files as a single changeset (`1903930`): add tail NIM provider to `providers.json`, tail slot to `combo-free-tools-heavy.json`, update four mapping descriptions to include "pinned NIM tail fallback", expand rebuild script to iterate over all five combo JSON files, delete two dead wrapper scripts. Validate JSON syntax (`python3 -m json.tool`) and Python syntax (`py_compile`) before commit. Delete `docs/remaining-dirty-changes.md` (not committed).
**Verify:** `git status` shows clean working tree. JSON configs pass `json.tool`. `rebuild-combos.py` passes `py_compile`. All repo references to deleted wrappers return empty.
**Retrospective:** Same lesson as §1: repo config and live SQLite are two separate surfaces. When editing live DB, always plan to sync JSON configs in the same session to prevent drift.

## §3 504: Readiness deadline vs deepseek slow prefill stall
**Symptom:** Codex FTS dashboard shows `504 POST /v1/responses` with `Total In=0 Total Out=0` and error `Stream produced no non-ping SSE event within 60000ms`. Dashboard shows long "duration" but that's Codex agentic turn accumulation; each round showed `deepseek succeeded (Xms, 0 fallbacks)` normally.
**Root cause:** Free NIM `deepseek-v4-pro` prefill >60s on large payload (~139K in + 25 tools) only sending ping keep-alives; OmniRoute readiness deadline (60s) judged stall. Combo step1/step2 both deepseek doubled the waste (step2 burned another 60-85s before falling to step3).
**Fix:** `STREAM_READINESS_MAX_TIMEOUT_MS` 60000 → **85000** in `~/Library/LaunchAgents/com.royalskynet.freetools-omniroute.plist`; combo dedup step2 to a different model (Nemotron Ultra free).
**Cross-layer boundary (critical):** Strip-proxy `RESPONSES_STREAM_IDLE_MS=90000`, and `server.mjs:264-268` resets idle timer on **any chunk including ping** → readiness deadline **must be < 90s** or strip-proxy kills first and combo fallback never triggers. 85s is the safe ceiling. Raising further requires raising strip-proxy idle in tandem.
**Verify:** `ps eww <pid> | grep READINESS` shows 85000; app.log stall should fallback to a **different model** (not deepseek again).
**Stats baseline:** deepseek succeeded 2992 / failed 689 (~18.7%), `no non-ping` events 107.

## §4 502: Omniroute orphan + bootstrap vs kickstart
**Symptom:** Strip-proxy `/_proxy/status`=200 but Codex receives 502; `curl 127.0.0.1:20128/v1/models` returns `000`; `lsof -iTCP:20128` empty.
**Root cause:** Omniroute was **not managed by launchd** (orphan process). `launchctl print gui/$(id -u)/com.royalskynet.freetools-omniroute` → `Could not find service ... 501`. Meanwhile `kickstart -k` **only restarts the process, does NOT re-read plist**, so plist env change (`STREAM_READINESS_MAX_TIMEOUT_MS=85000`) never took effect while process ran.
**Fix:** `plutil -lint` validate plist → `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.royalskynet.freetools-omniroute.plist` (RunAtLoad=true starts it).
**Rule (key knowledge):**
- Change **plist env** → **MUST `bootstrap`** (reloads definition)
- Change **live DB combo** → `kickstart -k` suffices (restart re-reads DB)
**Guard boundary:** `~/.claude/hooks/guard.js:91` blocks `launchctl (unload|remove|bootout)`; **does NOT block `bootstrap` / `kickstart`** → restarting dead service needs no `GUARD_OK=1`.
Also note: guard blocks "local admin API with API key sent out" → query combo via `sqlite3 ~/.omniroute/storage.sqlite` directly, not via admin API with credentials.
**Verify:** `launchctl list | grep omniroute` shows pid; 20128 `/v1/models`=200; strip-proxy=200.

## §5 §3's 85000 fix silently reverted to 30000 by a later install-launchd.sh re-run
**Symptom:** After `npm update -g omniroute` (3.8.48→3.8.49, unrelated routine upgrade), baseline check of live plist showed `STREAM_READINESS_MAX_TIMEOUT_MS=30000` / `STREAM_READINESS_TIMEOUT_MS=20000` instead of the §3 fix's 85000.
**Root cause:** §3's fix was applied as a **direct edit to the live plist**, never fed back into `guardian/com.royalskynet.freetools-omniroute.plist.tmpl` (still had the original 30000/20000 defaults). `guardian/install-launchd.sh` sed-substitutes the template's literal values straight into the installed plist — no separate override layer. A later re-run of `install-launchd.sh` (around the Block C/D/E harness work, commit `3898ed8`) regenerated the plist from the stale template and silently dropped the 85000 fix back to 30000. `git log -S "85000"` across the whole repo found zero hits — the value never existed in version control, only live.
**Fix:** Edit `guardian/com.royalskynet.freetools-omniroute.plist.tmpl` to 85000 (commit `5d53a8d`) so the template is now the source of truth; re-run `install-launchd.sh` to regenerate the plist; `launchctl kickstart -k gui/$(id -u)/com.royalskynet.freetools-omniroute` to force the running process to pick up the new env (matches §4's kickstart-vs-bootstrap rule — kickstart alone doesn't re-read plist, but `install-launchd.sh`'s bootstrap already reloaded the definition, so kickstart here just restarts into it).
**Rule (key knowledge):** Any live-only plist/env tuning fix **must** be written back into its `.tmpl` in the same session, or the next `install-launchd.sh` run reverts it with zero warning. Same repo-vs-live-drift lesson as §1/§2, but this time repo (stale) beat live (correct) instead of the other way round.
**Verify:** `ps eww <pid> | grep STREAM_READINESS_MAX_TIMEOUT_MS` shows 85000 on the pid currently held by `launchctl list | grep omniroute`; `git log -S "85000" -- guardian/` now shows a hit.
