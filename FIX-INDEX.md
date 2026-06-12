# FIX-INDEX

Personal bug runbook — symptom → fix lookup, adr-tools style.

## Quick start

```bash
fixindex find "<symptom keyword>"   # match frontmatter `symptoms:` across fix files
fixindex show 0001                  # cat fixes/0001-*.md
fixindex list                       # all entries
fixindex grep "<keyword>"           # full-text ripgrep including bodies
fixindex new <slug>                 # scaffold next-numbered fix file
fixindex re-index                   # regenerate the directory table below (idempotent)
fixindex supersede <old> <new>      # mark old superseded by new
```

Each fix lives in `fixes/NNNN-<slug>.md` with a YAML frontmatter (`id / slug / title / tags / symptoms[] / status / supersedes[] / related[]`) and one or more `## §N {title}` sections shaped as **Symptom / Root cause / Fix / Verify**.

## Directory

<!-- fixindex:table:start -->
| ID | Slug | Title | Tags |
|----|------|-------|------|
| 0001 | lark-meeting-notes | lark-meeting-notes / audio-meeting-notes 摘要與 LLM 卡住 | lark, meeting-notes, llm, spawnSync |
<!-- fixindex:table:end -->

## Adding entries

- **Same domain, new symptom:** append a `## §N` section to the matching fix file and add the symptom string to its frontmatter `symptoms:` array — that's what `fixindex find` scans.
- **New domain (≥3 expected entries):** `fixindex new <slug>` to scaffold + auto-bump the ID.
- **Deprecate:** `fixindex supersede <old> <new>` — flips `status:` to `superseded` and records the back-link; never delete the file.
