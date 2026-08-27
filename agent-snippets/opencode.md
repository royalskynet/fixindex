# Bug runbook integration (fixindex)

Before debugging any failure, run `fixindex find "<symptom keyword>"`.
Triggers: user names a system + a symptom, uses a failure verb
("broken / silent / timing out / crashing"), or pastes an error or log.
Read the matching `fixes/NNNN-*.md` before writing or editing code. If
`find` returns nothing, fall back to general exploration.

After solving a new bug, record it with a single pipe (no hand-appending):
`printf 'SYMPTOM: ...
ROOT: ...
FIX: ...
VERIFY: <rerunnable command>' | fixindex fi`
`fixindex fi` is free-text tolerant (no KEY lines needed: `echo '...' | fixindex fi`); it
auto-dedups, appends a new `## §N` to the best-matching domain file (or creates a new entry
if none fits), re-indexes, and commits. Never hand-append `## §N` or edit `symptoms:`.

Write an entry only when you have **fixed a defect** — not when a phase,
task, or session completes. *Symptom before narrative*: if you cannot write
a Symptom someone would grep for, you have a status report, not an entry.
Never write dates into filenames, "correction (date)" sections (edit the
original in place), Verify as a one-off reading (it must be a rerunnable
command with an expected result), Fix as project progress ("fixed in
Phase 3"), metrics or PIDs in `symptoms:`, several defects in one entry,
sign-off checklists, or secrets — not even a truncated key prefix.

Record an entry as you wrap up any substantial task — provided it actually
fixed a defect. When you miss one, the user types a bare `fi` (nothing else
in the message): that means record what this conversation just produced,
right now. Do not ask what to write and do not run `list` at them — one
clarifying question and the point is lost. Write the
root-cause formula, supporting data, paths already ruled out, and any
portable rule — not a changelog. Record it even when the fix is not
implemented yet: say "not fixed" and note the next step.
**Which repo `fi` writes to:** `fixindex fi` writes to the fixes dir pointed to by
`FIXINDEX_DIR` (fallback: the CLI repo's `fixes/`, which is gitignored — your entry
would be silently ignored). In shell-free/scheduler contexts the env var may not be
sourced from `.zshrc`; before recording, confirm `$FIXINDEX_DIR` resolves to your
intended runbook (e.g. `~/notes/runbook/fixes`) or export it explicitly. Never
`git add -f` an ignored entry — that is a signal you wrote to the wrong repo.


The user may also use the explicit keyword `Fixindex <question>` to
force an entry. Dispatch by intent: `list` / `find` / `show` / `grep` /
`new` / `supersede`. Decision order: `list` first to spot the matching
domain, then run the specific subcommand. Never `grep` blindly when the
user named a system that maps cleanly to an existing fix file.
