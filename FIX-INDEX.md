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

Each fix lives in `fixes/NNNN-<slug>.md` with a YAML frontmatter (`id / slug / title / tags / symptoms[] / status / supersedes[] / related[]`) and one or more `## §N {title}` sections shaped as **Symptom / Root cause / Fix / Verify / Retrospective** (Retrospective optional — record only when there is a lesson worth carrying forward).

## Directory

<!-- fixindex:table:start -->
| ID | Slug | Title | Tags |
|----|------|-------|------|
| 0001 | deploy-pipeline | Deploy pipeline / CI runner / artifact upload | ci,deploy,docker,github-actions |
| 0002 | postgres-migrations | PostgreSQL migrations / locking / connection pool | postgres,migrations,locking,connection-pool |
| 0003 | tls-and-tunnels | TLS / reverse proxy / tunnel webhook drift | tls,nginx,cloudflare,tunnel,webhook |
<!-- fixindex:table:end -->

## Adding entries

- **Same domain, new symptom:** append a `## §N` section to the matching fix file and add the symptom string to its frontmatter `symptoms:` array — that's what `fixindex find` scans.
- **New domain (≥3 expected entries):** `fixindex new <slug>` to scaffold + auto-bump the ID.
- **Deprecate:** `fixindex supersede <old> <new>` — flips `status:` to `superseded` and records the back-link; never delete the file.
