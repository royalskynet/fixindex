# fixindex

> A feather-weight, file-only personal bug runbook — symptom → fix lookup, in the spirit of `adr-tools`.

[繁體中文 README](./README.zh-TW.md)

`fixindex` is ~150 lines of `bash` + `ripgrep`. No database, no daemon, no editor plugin. Every fix you ever solve goes into one Markdown file under `fixes/NNNN-<slug>.md`. The next time the same error message hits your terminal, `fixindex find "<error>"` jumps straight to the fix you wrote last quarter.

It exists because:

- Most personal "second brain" tools are too heavy. You want one command and the answer on stdout.
- LLM coding agents (Claude Code, Codex, etc.) waste tokens re-discovering bugs you already solved. Pointing them at `fixindex find` before they start exploring saves hours of re-debugging.

## Install

```bash
# 1. Clone or vendor into a personal notes repo
git clone https://github.com/royalskynet/fixindex.git ~/dev/fixindex
cd ~/dev/fixindex

# 2. Put the CLI on PATH
ln -s "$PWD/fixindex" ~/.local/bin/fixindex
# or: echo 'export PATH="$HOME/dev/fixindex:$PATH"' >> ~/.zshrc

# 3. Point it at your runbook (skip if you'll just `cd` into this repo)
export FIXINDEX_DIR="$HOME/notes/runbook/fixes"
export FIXINDEX_INDEX="$HOME/notes/runbook/FIX-INDEX.md"
```

Requirements: `bash` 4+, `ripgrep` (`brew install ripgrep`), `awk`, `find`. macOS and Linux. No Node, no Python required for the CLI itself.

## Workflow

### When a bug hits

```bash
$ fixindex find "deadlock detected"
## symptoms match:
  0002-postgres-migrations        L7       - "ERROR: deadlock detected"

(use `fixindex grep 'deadlock detected'` for full-text search)

$ fixindex show 0002
# 0002 postgres-migrations
…
## §1 ALTER TABLE blocks on long-running transaction
**Symptom:** Migration hangs forever on `ALTER TABLE … ADD COLUMN`…
**Root cause:** Another session holds an `AccessShareLock`…
**Fix:** Set a lock timeout before the migration, retry-on-failure:
…
```

### After you solve something new

1. Either append a `## §N` block to an existing domain file and add the symptom string to its frontmatter `symptoms:` array,
2. or scaffold a brand-new domain:

```bash
$ fixindex new redis-cluster
/path/to/fixes/0004-redis-cluster.md
re-indexed: /path/to/FIX-INDEX.md
```

Then edit `fixes/0004-redis-cluster.md`, fill in `Symptom / Root cause / Fix / Verify`, and you're done.

### File shape

Each fix file looks like this (template at `fixes/.template.md`):

```markdown
---
id: 0002
slug: postgres-migrations
title: PostgreSQL migrations / locking / connection pool
tags: [postgres, migrations, locking]
symptoms:
  - "ERROR: deadlock detected"
  - "could not obtain lock on relation"
  - "remaining connection slots are reserved"
status: active
supersedes: []
related: []
---
# 0002 postgres-migrations

## §1 ALTER TABLE blocks on long-running transaction
**Symptom:** …
**Root cause:** …
**Fix:** …
**Verify:** …
**Retrospective:** (optional) Why didn't a prior fix catch this? Skip when there is no lesson.
```

The frontmatter `symptoms:` array is the **search index** — it's what `fixindex find` scans for. Treat it as a list of error-message strings you'd type into your shell. The body of each `## §N` block is the human-readable runbook. The **Retrospective** row is borrowed from Trellis's debug-retrospective step — record it only when the bug recurred or a prior fix should have caught it.

## Commands

| Command | What it does |
|---------|--------------|
| `fixindex find <kw>` | Match `<kw>` against frontmatter `symptoms:` entries. First stop. |
| `fixindex grep <kw>` | Full-text ripgrep across all fix files. Use when `find` misses. |
| `fixindex show <id>` | `cat fixes/NNNN-*.md`. |
| `fixindex list` | One-line summary per fix. |
| `fixindex new <slug>` | Allocate the next ID, scaffold the file, refresh the index table. |
| `fixindex re-index` | Regenerate the `<!-- fixindex:table -->` block in `FIX-INDEX.md`. Idempotent. |
| `fixindex supersede <old> <new>` | Mark `<old>` superseded by `<new>` without deleting it. |
| `fixindex help` | Show the help. |

Environment overrides: `FIXINDEX_DIR`, `FIXINDEX_INDEX`, `RG`.

## Using fixindex with an LLM coding agent

If you use Claude Code or a similar agent, the goal is **the agent runs `fixindex` automatically — you never type the CLI by hand**.

**Drop-in snippets** per platform live in [`agent-snippets/`](./agent-snippets/) — pick the file for your tool (Claude / Codex / Cursor / Gemini / opencode / generic) and `cat … >> <your-rules-file>`. Pattern borrowed from Trellis's multi-platform config layout.

See [`docs/agent-integration.md`](./docs/agent-integration.md) for the full natural-language dispatch table:

- **Mode A — explicit keyword `Fixindex <question>`**: agent picks `find / show / grep / new / supersede / list` from your intent.
- **Mode B — implicit NL triggers**: any system name + symptom, failure verb ("broken / silent / timing out"), or pasted error/log autoruns `fixindex find` *before* the agent starts exploring. Any "fixed it / log this / remember this" autoappends a `## §N` block.

A drop-in snippet for your agent's global instructions is at the bottom of that doc.

This converts "let me explore the repo from scratch" into "let me check the runbook first" — and stops the agent from re-deriving the same fix month after month.

## Why feather-weight?

Other approaches considered, and why they're not here:

- **SQLite / vector DB.** Adds a binary blob to your dotfiles and a daemon to maintain. `ripgrep` over ~30 markdown files is already sub-50 ms.
- **Editor plugin.** Locks you into one editor. The CLI works in any terminal, including over SSH and inside an agent's `bash` tool.
- **One file per fix (pure adr-tools style).** Personal bug logs explode into hundreds of single-paragraph files. Grouping by *domain* (`postgres-migrations.md` holding 10 related fixes) keeps the file count under control without losing granularity — each `## §N` block is still independently linkable.
- **LLM-generated summaries / auto-tagging.** Non-deterministic. The frontmatter is the index — you write it once, by hand, and trust it forever.

## License

MIT — see [LICENSE](./LICENSE).

## Prior art

- [npryce/adr-tools](https://github.com/npryce/adr-tools) — the numbering + auto-index pattern.
- [danluu/post-mortems](https://github.com/danluu/post-mortems) — proof that plain markdown is enough.
- [tldr-pages](https://github.com/tldr-pages/tldr) — symptom-first lookup as a UX primitive.
