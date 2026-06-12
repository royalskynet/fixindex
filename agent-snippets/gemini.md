# Bug runbook integration (fixindex)

Before debugging any failure, run `fixindex find "<symptom keyword>"`.
Triggers include: user names a system + a symptom, uses a failure verb
("broken / silent / timing out / crashing"), or pastes an error or log.
Read the matching `fixes/NNNN-*.md` before writing or editing code. If
`find` returns nothing, fall back to general exploration.

After solving a new bug, append a `## §N {title}` block to the matching
fix file using the Symptom / Root cause / Fix / Verify / Retrospective
shape (Retrospective optional — record only a lesson worth carrying),
and add the new symptom string to the frontmatter `symptoms:` array.
For a brand-new domain, run `fixindex new <slug>` and fill the scaffold.

The user may also use the explicit keyword `Fixindex <question>` to
force an entry. Dispatch by intent: `list` / `find` / `show` / `grep` /
`new` / `supersede`. Decision order: `list` first to spot the matching
domain, then run the specific subcommand. Never `grep` blindly when the
user named a system that maps cleanly to an existing fix file.
