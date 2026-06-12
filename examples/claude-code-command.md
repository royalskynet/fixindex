---
description: Search personal bug runbook with natural language — model picks the right fixindex subcommand
argument-hint: <natural language symptom or query>
allowed-tools: Bash
---

# /fixindex — Bug Runbook Lookup

Query: $ARGUMENTS

## Your job

Read the query and pick the best fixindex subcommand:

| Intent | Command |
|--------|---------|
| Symptom / error phrase → search frontmatter | `fixindex find <keyword>` |
| General keyword → full-text search | `fixindex grep <keyword>` |
| Browse everything | `fixindex list` |
| Know the ID already | `fixindex show <id>` |

Rules:
- Extract 1–3 keywords from the query (CJK OK)
- Prefer `find` when query looks like a symptom; `grep` when broader
- Run multiple commands if one returns nothing
- Show results verbatim, then one-line summary of the most relevant fix
- If nothing found: say so, offer `fixindex new <slug>` to record it

Env already set globally: `FIXINDEX_DIR`, `FIXINDEX_INDEX`.
Binary: `~/.local/bin/fixindex`
