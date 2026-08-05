# Bug runbook integration (fixindex)

Before debugging any failure, run `fixindex find "<symptom keyword>"`.
Triggers: user names a system + a symptom, uses a failure verb
("broken / silent / timing out / crashing"), or pastes an error or log.
Read the matching `fixes/NNNN-*.md` before writing or editing code. If
`find` returns nothing, fall back to general exploration.

After solving a new bug, append a `## §N {title}` block to the matching
fix file using the Symptom / Root cause / Fix / Verify / Retrospective
shape (Retrospective optional — record only a lesson worth carrying),
and add the new symptom string to the frontmatter `symptoms:` array.
For a brand-new domain, run `fixindex new <slug>` and fill the scaffold.

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
clarifying question and the point is lost. Judge the domain, `find` for a
closer existing file, append `## §N` (or `fixindex new <slug>`), extend
`symptoms:`, and `re-index` only if you created a file. Write the
root-cause formula, supporting data, paths already ruled out, and any
portable rule — not a changelog. Record it even when the fix is not
implemented yet: say "not fixed" and note the next step.

The user may also use the explicit keyword `Fixindex <question>` to
force an entry. Dispatch by intent: `list` / `find` / `show` / `grep` /
`new` / `supersede`. Decision order: `list` first to spot the matching
domain, then run the specific subcommand. Never `grep` blindly when the
user named a system that maps cleanly to an existing fix file.
