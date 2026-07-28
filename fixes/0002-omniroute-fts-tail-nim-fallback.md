---
id: 0002
slug: omniroute-fts-tail-nim-fallback
title: OmniRoute FTS combo tail NIM fallback
tags: [omniroute, fts, combo, nvidia-nim]
symptoms:
  - "dead placeholder wrapper scripts"
  - "rebuild-combos.py only rebuilds 2 combos not 5"
  - "dirty changes after live DB edit"
  - "repo config JSON out of sync with live SQLite combo"
  - "FTS OmniRoute combo needs another NIM after OpenRouter free"
  - "free-tools-heavy OpenRouter free tail fallback should continue to pinned NIM"
  - "add NVIDIA NIM key as final fallback in free-tools-heavy"
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
