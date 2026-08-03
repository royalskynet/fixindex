---
id: 0041
slug: mannieselftasks-20260802-completed
title: Mannie self-tasks 2026-08-02 completed — M3, T1–T3, T5
tags: [mannie, hermes-agent, kanban, strip-proxy, test, admission-busy, fallback]
symptoms:
  - "mannie_consolidate.py KeyError: 'written' on early return"
  - "503 admission-busy errors not covered by regression tests"
  - "background_review tool whitelist deny message missing tool names"
  - "_is_model_incompatible_error and fallback path not tested"
  - "_is_invalid_aux_response_error and _try_payment_fallback edge cases not tested"
  - "kanban _inherit_notify_subs omits chat_type and delivery_metadata"
  - "strip-proxy pure functions lack unit tests"
status: active
supersedes: []
related:
  - 0037-omniroute-503-chat-admission-busy
---
# 0041 mannieselftasks-20260802-completed

## §1 mannie_consolidate.py KeyError: 'written' on early return
**Symptom:** `mannie_consolidate.py` exits with `KeyError: 'written'` when no tasks need consolidation (early return at line 142).
**Root cause:** Early return path returned dict with only `processed` and `watermark` keys, missing `written` key that downstream code expects.
**Fix:** Added `"written": 0` to early return dict. Updated docstring to match return schema.
**Verify:** `python scripts/mannie_consolidate.py` → `consolidate: processed=0 written=0 watermark=21`, exit 0.

## §2 503 admission-busy regression test suite (T1)
**Symptom:** No formal regression tests for OmniRoute admission-busy 503 detection/retry logic; previous offline verification not committed.
**Root cause:** `_is_admission_busy_error` (3 occurrences in auxiliary_client.py) and related retry logic had no pytest coverage.
**Fix:** Created `tests/agent/test_admission_busy.py` with 30 tests covering: 3×503 shape detection, non-admission 503 rejection, cross-classifier regression guards (admission never misclassified as payment/rate-limit/connection/model-not-found), Retry-After parsing (clamp, default, case-sensitivity).
**Verify:** `venv/bin/pytest tests/agent/test_admission_busy.py -v` → 30 passed.

## §3 background_review tool whitelist deny message (T2 module 1)
**Symptom:** `set_thread_tool_whitelist` deny message used placeholder format but tests didn't verify all four tool names (memory, skills_list, skill_view, session_search) were present.
**Root cause:** Whitelist logic in `background_review.py:859-881` combines skills (3 tools) + memory (1 tool) = 4 tools; deny message at line 875 uses `{tool_name}` placeholder formatted at runtime.
**Fix:** Created `tests/agent/test_background_review_whitelist.py` with 7 tests verifying: whitelist contains exactly 4 tools, deny message includes all 4 names, placeholder is `{tool_name}` (not literal), format matches `background_review.py:875-881`, memory-disabled case has 3 tools.
**Verify:** `venv/bin/pytest tests/agent/test_background_review_whitelist.py -v` → 7 passed.

## §4 _is_model_incompatible_error and fallback path (T2 module 2)
**Symptom:** 400-class capability-mismatch errors (model not supported, context window exceeded, etc.) should trigger provider fallback, but fallback path untested.
**Root cause:** `_is_model_incompatible_error` checks for 6 positive keywords and excludes 3 categories; `should_fallback` adds `is_capacity_error=True` for incompatible errors, allowing fallback even with explicit provider.
**Fix:** Created `tests/agent/test_model_incompatible_fallback.py` with 17 tests covering: 6 positive keywords, exclusion of model-not-found/billing/other errors, fallback path triggers on incompatible error, explicit provider still falls back when `is_capacity_error=True`.
**Verify:** `venv/bin/pytest tests/agent/test_model_incompatible_fallback.py -v` → 17 passed.

## §5 _is_invalid_aux_response_error and _try_payment_fallback edge cases (T2 module 3)
**Symptom:** Invalid SSE response errors and payment fallback chain edge cases (empty chain, unhealthy skip, resolve failure, exhaustion) untested.
**Root cause:** `_is_invalid_aux_response_error` detects 5 error patterns; `_try_payment_fallback` iterates provider chain with health checks, skips unhealthy, handles `(None, None)` returns, exhausts chain.
**Fix:** Created `tests/agent/test_invalid_aux_response_and_payment_fallback.py` with 12 tests covering: 5 invalid response patterns, empty chain returns None, unhealthy provider skipped, try_fn returning (None, None) moves to next, exhausted chain returns None.
**Verify:** `venv/bin/pytest tests/agent/test_invalid_aux_response_and_payment_fallback.py -v` → 12 passed.

## §6 kanban _inherit_notify_subs column mismatch (T3)
**Symptom:** Child task notifications inherited from parent had `chat_type=NULL` and `delivery_metadata=NULL`, breaking Telegram topic routing.
**Root cause:** `add_notify_sub` (line 9644) uses 10 columns including `chat_type` and `delivery_metadata`; `_inherit_notify_subs` (line 3321) INSERT...SELECT used only 8 columns, omitting the two new columns added by migration.
**Fix:** Updated `_inherit_notify_subs` INSERT...SELECT to include `chat_type` and `delivery_metadata` (lines 3322-3324, 3327), matching `add_notify_sub` schema. Added `tests/hermes_cli/test_inherit_notify_subs.py` with 3 tests verifying inheritance preserves both columns, multiple parents combined, OR IGNORE skips duplicates.
**Verify:** `venv/bin/pytest tests/hermes_cli/test_inherit_notify_subs.py -v` → 3 passed.

## §7 strip-proxy pure function unit tests (T5)
**Symptom:** strip-proxy `server.mjs` contained 20+ pure functions (stripControlTokens, stripReasoningPlaceholder, removeTaggedBlocks, extractResponsesText, responsesObjectHasToolSignal, analyzeResponsesSSECompletion, isDegenerateCore, isTagWrappedDegenerate, extractClaudeSessionId, extractSessionHint, claudeProfileForRequest, trailingSentinelPrefixLen, etc.) with no unit tests.
**Root cause:** Pure functions mixed with I/O-bound server code; no test infrastructure for isolated function verification.
**Fix:** Created `test-pure-functions.mjs` with 67 unit tests covering all extracted pure functions. Tests run with `node test-pure-functions.mjs` (no external dependencies).
**Verify:** `node test-pure-functions.mjs` → 67 passed, 0 failed.