# fixindex

> Featherweight, file-only personal bug runbook — symptom → fix lookup in one command, inspired by `adr-tools`.

[中文說明](./README.md)

`fixindex` is ~150 lines of `bash` + `ripgrep`. No database, no daemon, no editor plugin. Every bug you've solved lands in a Markdown file `fixes/NNNN-<slug>.md`. Next time the same error message appears, `fixindex find "<error>"` jumps straight to the fix you wrote last quarter.

Why it exists:

- Most "second brain" tools are too heavy. You want one command, answer straight to stdout.
- LLM coding agents (Claude Code, Codex…) re-explore bugs you've already solved, burning tokens. Point them at `fixindex find` before they start digging — saves hours of repeated debugging.

## Install

```bash
# 1. clone or embed into your personal notes repo
git clone https://github.com/royalskynet/fixindex.git ~/dev/fixindex
cd ~/dev/fixindex

# 2. put the CLI on PATH
ln -s "$PWD/fixindex" ~/.local/bin/fixindex
# or: echo 'export PATH="$HOME/dev/fixindex:$PATH"' >> ~/.zshrc

# 3. point at your runbook (skip if using this repo directly)
export FIXINDEX_DIR="$HOME/notes/runbook/fixes"
export FIXINDEX_INDEX="$HOME/notes/runbook/FIX-INDEX.md"
```

Requirements: `bash` 4+, `ripgrep` (`brew install ripgrep`), `awk`, `find`. macOS and Linux. No Node or Python needed.

## Workflow

### When you hit a bug

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

### After solving a new bug

1. Append a `## §N` section to the matching domain file and add the new symptom string to the frontmatter `symptoms:` array; or
2. Start a brand-new domain:

```bash
$ fixindex new redis-cluster
/path/to/fixes/0004-redis-cluster.md
re-indexed: /path/to/FIX-INDEX.md
```

Then edit `fixes/0004-redis-cluster.md` and fill in `Symptom / Root cause / Fix / Verify`.

### File structure

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
**Retrospective:** (optional) Why didn't the old fix catch this? Skip if no lesson.
```

The `symptoms:` array in frontmatter is the **search index** — that's what `fixindex find` actually scans. Think of it as "the error strings you'd type into the shell next time this happens." The `## §N` body is the human-readable runbook.

## Commands

| Command | What it does |
|---------|-------------|
| `fixindex find <kw>` | Match against frontmatter `symptoms:` entries. First stop. |
| `fixindex grep <kw>` | Full-text ripgrep across all fix files. Use when `find` misses. |
| `fixindex show <id>` | `cat fixes/NNNN-*.md`. |
| `fixindex list` | One-line summary per fix file. |
| `fixindex new <slug>` | Assign next ID, scaffold file, refresh index table. |
| `fixindex re-index` | Regenerate the `<!-- fixindex:table -->` block in `FIX-INDEX.md`. Idempotent. |
| `fixindex supersede <old> <new>` | Mark `<old>` superseded by `<new>`, keep file. |
| `fixindex help` | Show usage. |

Env vars: `FIXINDEX_DIR`, `FIXINDEX_INDEX`, `RG`.

## Natural language — no commands to memorize

After installing the agent snippet, you don't need to type `fixindex` by hand. Just talk to the agent naturally. It reads intent and picks the right subcommand:

| You say | Agent runs |
|---------|-----------|
| `Fixindex` or `Fixindex <question>` | Picks `find / show / grep / new / supersede / list` by intent |
| "postgres is hanging", "redis not responding" (system + symptom) | `fixindex find "<keyword>"` → reads the matching file |
| Pastes an error message, log line, or stack trace | `fixindex find "<first identifying string>"` |
| "How did we fix this last time?", "Any prior solution?" | `fixindex find` to search history |
| "Fixed it", "that worked", "log this fix" | Auto-appends `## §N` block + updates `symptoms:` array |
| Brand-new domain, no matching fix file | `fixindex new <slug>` → fills scaffold |

> **How it works**: The agent handles intent → selects command → executes CLI. `fixindex` itself stays a deterministic CLI — NL understanding lives in the agent layer, keeping the tool reliable.

Two trigger modes: **explicit keyword** (`Fixindex <question>`) when you want control; **implicit triggers** (naming a system + symptom, pasting a log, saying "fixed it") so the agent consults or records automatically without you having to remember.

## Using with LLM coding agents

**One-command snippets for all platforms** in [`agent-snippets/`](./agent-snippets/) — pick your tool (Claude / Codex / Cursor / Gemini / opencode / generic), `cat … >> <rules-file>` to install.

Full natural-language dispatch table (with examples and rationale) in [`docs/agent-integration.md`](./docs/agent-integration.md).

Turn "agent re-explores the whole repo" into "agent checks the runbook first" — the same fix doesn't get rediscovered every month.

## Why featherweight

Options considered and rejected:

- **SQLite / vector DB.** Extra binary in dotfiles, extra daemon to babysit. `ripgrep` across ~30 Markdown files is already < 50 ms.
- **Editor plugin.** Locks you to one editor. CLI works in any terminal, including SSH and an agent's `bash` tool.
- **One file per fix (pure adr-tools style).** A personal bug log quickly balloons to hundreds of single-paragraph files. Domain grouping (`postgres-migrations.md` holds 10 related fixes) keeps file count manageable without losing granularity — each `## §N` section is still independently referenceable.
- **LLM auto-summarize / auto-tag.** Non-deterministic. The frontmatter is the index — you write it once, you trust it forever.

## License

MIT — see [LICENSE](./LICENSE).

## Credits

- [npryce/adr-tools](https://github.com/npryce/adr-tools) — numbered records + auto-index pattern.
- [danluu/post-mortems](https://github.com/danluu/post-mortems) — proof that plain Markdown is enough.
- [tldr-pages](https://github.com/tldr-pages/tldr) — symptom-first lookup as a UX primitive.
