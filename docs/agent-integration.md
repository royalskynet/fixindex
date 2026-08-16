# Using fixindex with an LLM coding agent

This document is meant to be copy-pasted (or `@import`-ed) into the global instructions of an LLM coding agent — `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, or equivalent. The goal: **the agent runs `fixindex` automatically, the human never types the CLI by hand**.

There are two trigger modes: an **explicit keyword** and a set of **natural-language patterns**.

---

## Mode A — Explicit keyword: `Fixindex` (or `Fixindex <question>`)

When the user's message begins with the literal word `Fixindex`, the agent must run a `fixindex` subcommand as the first action. Pick the subcommand from the user's intent:

| User says | Agent runs |
|-----------|------------|
| `Fixindex` alone, no payload | `fixindex list` |
| `Fixindex <symptom / error / domain>` | `fixindex find "<keyword>"`, then read the matching `fixes/NNNN-*.md` |
| `Fixindex show NNNN` / mentions a specific ID | `fixindex show NNNN` |
| `Fixindex grep <inner detail>` (not a symptom you'd expect in the index) | `fixindex grep "<keyword>"` (full-text) |
| `Fixindex record <fix>` / `Fixindex log <fix>` / `Fixindex new entry` | `printf 'SYMPTOM: …\nROOT: …\nFIX: …\nVERIFY: …' | fixindex fi`（或指定 domain `fixindex fi <domain>`） |
| Brand-new domain, no existing fix file fits | `fixindex new <slug>` |
| `Fixindex supersede <old>` / `<old> replaced by <new>` | `fixindex supersede <old> <new>` |
| **`fi` — bare, nothing else in the message** | **Record what the conversation just produced.** See A.1 |
| No hit anywhere | Fall back to whatever memory/search tool you have (`mem-search`, vector DB, etc.) |

Decision order: **list first → pick subcommand**. Never blindly `grep` if the user mentioned a system name that maps cleanly to an existing fix file via `fixindex list`.

### A.1 `fi` — the catch-up keyword

You should already be recording an entry **as you wrap up any substantial task** — provided that task actually fixed a defect. `fi` exists for the times you didn't.

A bare `fi` (nothing else in the message) means: **write it down now.** Not `fixindex list`, not "what would you like me to record?" — this is the keyword a user reaches for at the moment they stop working, and one clarifying question destroys its entire value.

收到 `fi` → 立刻組 3–6 行摘要 pipe 給 `fixindex fi` 記下，不追問、不 `list`、不 `find`。`fixindex fi` 會自動 dedup、domain 匹配 append 新 `## §N`（無匹配則建新檔）、re-index、commit。

What to write: the **root-cause formula, supporting data, the paths already ruled out, and any portable rule**. Not a changelog of edits. **Record it even when the fix isn't implemented** — write "not fixed", note the next step, and stop. The diagnosis is the asset; it's what stops the next person re-deriving it.

```bash
printf 'SYMPTOM: ...\nROOT: ...\nFIX: ...\nVERIFY: <rerunnable command>' | fixindex fi
```
自由文字也行（`echo '一行症狀' | fixindex fi`）；指定 domain 的舊介面 `fixindex fi <domain>` 仍可用。

---

## Mode B — Implicit natural-language triggers

Even without the `Fixindex` keyword, the agent should call `fixindex` automatically whenever the user's message looks like a debugging or post-mortem moment.

### B.1 Read mode — before debugging

Trigger `fixindex find "<keyword>"` to load prior context **before** writing or editing any code.

| Phrase pattern | Action |
|----------------|--------|
| User names a system you have a fix file for (`postgres`, `nginx`, `redis`, etc.) and describes a symptom | `fixindex find "<system + symptom>"` |
| Failure verbs: "broken", "not working", "silent", "stuck", "timing out", "crashing" | `fixindex find "<verb-phrase>"` |
| User pastes an error message, stack trace, or log line | `fixindex find "<first identifying string of the error>"` |
| "Why does X do Y?" / "How did we fix this last time?" | `fixindex find` + read the hit |

After the hit, read `fixes/NNNN-<slug>.md` directly. No need to `show` separately if you already know which file.

If `find` returns nothing, *then* fall back to general exploration tools.

### B.2 Write mode — after solving

Trigger an **append** without waiting for the user to ask.

| Phrase pattern | Action |
|----------------|--------|
| "Fixed it", "got it working", "that did it", "solved", "we're good" | Append a `## §N` block to the matching `fixes/NNNN-*.md`; add the new symptom string to frontmatter `symptoms:` |
| "Log this", "remember this", "add to the runbook", "write this down" | Same as above |
| New failure mode that doesn't fit any existing domain | `fixindex new <slug>`, then fill the scaffold |

Append shape — match the existing convention exactly:

```markdown
## §N One-line title
**Symptom:** `exact error string` or specific user-visible behavior
**Root cause:** One sentence — the underlying mechanism, not the trigger
**Fix:** The smallest change that resolves it (command / diff / config)
**Verify:** The observation that confirms it worked
```

After the append, run `fixindex re-index` only if you created a new file (B.2 row 3). Appending within an existing file does not change the directory table.

### B.3 What counts as an entry — symptom before narrative

A fix log is a **reproducible, work-saving technical note**, not a record of what happened.

Write an entry when you have **fixed a defect**. Not when a phase completed, a task shipped, or a session wrapped up. Diagnosis without a fix still qualifies — write it, mark it "not fixed yet", and record the next step; the diagnosis is the asset that stops the next person re-deriving it.

The test is mechanical: **if you cannot write a `Symptom` that someone would plausibly type into a search box, you do not have an entry.** You have a status report. Put it somewhere else.

| Don't | Why | Instead |
|---|---|---|
| Dates in filenames — `0042-thing-20250105.md` | The entry is about the defect, not the day | `0042-thing.md` |
| `## §N Correction (date)` sections | Amending your own earlier write-up is a conversation artifact | Edit §1 in place |
| `Verify` as a one-off reading — "quota 348/1000, error rate 2.3%" | Tomorrow it reads differently and proves nothing | A rerunnable command **plus its expected result** |
| `Fix` as project progress — "Phase 3 introduced the new pool", "fixed in Block B" | Meaningless once that document is gone | The command or the diff |
| Metrics in `symptoms:` — "50.8% / 49.2%", "PID 81681", "6 occurrences on 2025-01-05" | Nobody will ever type that into a search | Only strings you would actually grep |
| Several defects in one entry | Breaks one-entry-per-defect; sections that share only an afternoon | Split them |
| Sign-off checklists — F1 ✅ / F2 ✅ / PIDs unchanged | Stale within hours | Omit; keep the rerunnable Verify |
| Pointers to throwaway docs — "see Block B of plan-xyz.md" | External docs disappear | Inline what matters |
| Secrets, even truncated key prefixes | Never justified "to show which one it was" | Reference the variable name |

**Why this matters.** Entries written symptom-first stay useful for years — someone hits the same error string and lands straight on the answer. Entries written narrative-first become unsearchable the moment you forget the project vocabulary, and they push the real fixes down the index. One is a runbook; the other is a diary.

**A note on phase-based workflows.** If your process says "each phase updates the runbook", resist mapping phases onto entries. A phase that fixed three defects produces three entries; a phase that fixed none produces zero. Phase-driven writing is the single most reliable way to fill a runbook with diaries.

---

## Mode C — Hook-enforced three-point loop (Claude Code reference implementation)

Modes A and B rely on the model remembering to fire. Under load it forgets. If your agent supports lifecycle hooks (Claude Code does), enforce the loop at exactly **three points** — not "on every action" (too noisy) and not "only before planning" (blind to what you hit mid-run):

| Point | Hook event | What fires |
|---|---|---|
| 1. Plan start — static sweep | `PreToolUse` on `ExitPlanMode` | If the session has run no `fixindex find` yet, inject a one-shot reminder: domain-level find on the plan's topic + toolchain, plus pre-query the foreseeable failure symptoms (external services, permissions, timeouts, stale state). Runs once, never nags. |
| 2. Mid-run — on-failure lookup | `PreToolUse` on `Bash`, mounted on the consecutive-failure counter | When a command fingerprint has already failed ≥1 time and the agent is about to retry, the hook itself runs `fixindex find "<last failure symptom>"` and injects the hits into context before the retry. At ≥2 failures the stop-loss notice takes over. |
| 3. Wrap-up — fi gate | `Stop` | If the transcript looks like a debug session (≥10 tool calls + error markers) and no `fixindex fi/new/auto` was run, return `{"decision":"block"}` to force a catch-up entry (or a one-line "nothing to record"). Guard with `stop_hook_active` to prevent loops; stay silent for small tasks below the call threshold. |

Properties: no failure → no trigger, so frequency is naturally bounded; mines the plan-time sweep can't see are caught the moment you step on them (point 2 covers the mid-run blind spot).

Reference implementation: [`hooks/plan-path-notice.js` and `hooks/fi-reminder.sh` in Ether-prompt](https://github.com/royalskynet/Ether-prompt/tree/main/hooks).

Two hard-won implementation notes: (a) `PostToolUse` does **not** fire when a Bash command exits non-zero and its payload has no exit code — read `is_error` from the session transcript instead; (b) time your `fixindex find` before embedding it in a hook (measured ~2.8 s) and give the subprocess timeout 1.5× headroom, or every lookup silently returns empty.

三點式（中文摘要）：① plan 起點域級掃雷（一次性，含預判高機率踩雷點）② 執行期踩雷當下、重試前以上次失敗症狀自動查 fixindex ③ 完工 Stop hook 擋收尾強制補 `fi`（小任務低於呼叫數門檻則靜默）。不失敗不觸發，頻率天然有界。

---

## Why two modes

- **Mode A** (the keyword) is for moments the user wants explicit control — "go check the runbook for this thing I'm about to describe".
- **Mode B** (the NL triggers) is for the much larger fraction of conversations where the user has already started debugging mid-message and would be annoyed at typing `Fixindex` every time.

Missing Mode B is the failure case that defeats the whole point of `fixindex`: the agent re-discovers the same fix you wrote last quarter, burns 20 minutes of conversation, and you wonder why you bothered writing the runbook at all.

---

## Snippet to drop into your agent's global instructions

```markdown
## Bug runbook integration (fixindex)

Before debugging any failure, run `fixindex find "<symptom keyword>"`. Triggers
include: user names a system + a symptom, user uses a failure verb
("broken/silent/timing out"), or user pastes an error/log. Read the matching
fixes/NNNN-*.md before writing or editing code. If find returns no match,
fall back to general exploration.

After solving a new bug, record it with a single pipe:
`printf 'SYMPTOM: ...\nROOT: ...\nFIX: ...\nVERIFY: <rerunnable command>' | fixindex fi`
(`fixindex fi` auto-dedups, appends a new `## §N` to the matching domain file — or creates a
new entry if none fits — re-indexes, and commits; free text like `echo '...' | fixindex fi`
also works. Don't hand-append `## §N` or edit `symptoms:`.)

Write an entry only when you have fixed a defect — not when a phase, task,
or session completes. Symptom before narrative: if you cannot write a Symptom
someone would grep for, you have a status report, not an entry. Never write
dates into filenames, "correction (date)" sections (edit the original in
place), Verify as a one-off reading (it must be a rerunnable command with an
expected result), Fix as project progress ("fixed in Phase 3"), metrics or
PIDs in `symptoms:`, several defects in one entry, sign-off checklists, or
secrets — not even a truncated key prefix.

Record an entry as you wrap up any substantial task — provided it actually
fixed a defect. When you miss one, the user types a bare `fi` (nothing else
in the message): that means record what this conversation just produced,
right now. Do not ask what to write and do not run `list` at them. Write the
root-cause formula, supporting data, paths already ruled out, and any
portable rule — not a changelog. Record it even when the fix is not
implemented yet: say "not fixed" and note the next step.

The user may also use the explicit keyword `Fixindex <question>` to force
an entry. Dispatch by intent: find / show / grep / new / supersede / list.
```
