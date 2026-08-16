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

## What belongs here — symptom before narrative

A fix log holds **reproducible, work-saving technical notes**, not a record of what happened.

**Write an entry after you fix a defect.** Not when a phase completed, a task shipped, or a session wrapped up. Diagnosis without a fix still counts — write it, mark it "not fixed yet", and record the next step; the diagnosis is the asset that stops the next person re-deriving it.

The test is mechanical: **if you can't write a `Symptom` someone would plausibly type into a search box, you don't have an entry.** You have a status report. Put it somewhere else.

| Don't | Why | Instead |
|---|---|---|
| Dates in filenames — `0042-thing-20250105.md` | The entry is about the defect, not the day | `0042-thing.md` |
| `## §N Correction (date)` sections | Amending your own earlier write-up is a conversation artifact | Edit §1 in place |
| `Verify` as a one-off reading — "quota 348/1000, error rate 2.3%" | Tomorrow it reads differently and proves nothing | A rerunnable command **plus its expected result** |
| `Fix` as project progress — "Phase 3 introduced the new pool", "fixed in Block B" | Meaningless once that document is gone | The command or the diff |
| Metrics in `symptoms:` — "50.8% / 49.2%", "PID 81681", "6 occurrences on 2025-01-05" | Nobody will ever type that into a search | Only strings you'd actually grep |
| Several defects in one entry | Breaks one-entry-per-defect; those sections share only an afternoon | Split them |
| Sign-off checklists — F1 ✅ / F2 ✅ / PIDs unchanged | Stale within hours | Drop them; keep the rerunnable Verify |
| Pointers to throwaway docs — "see Block B of plan-xyz.md" | External docs disappear | Inline what matters |
| Secrets, even a truncated key prefix | "To show which one it was" is never a reason | Reference the variable name |

**Why this matters.** Entries written symptom-first stay useful for years — someone hits the same error string and lands straight on the answer. Entries written narrative-first become unsearchable the moment you forget the project's vocabulary, and they push the real fixes down the index. One is a runbook; the other is a diary.

**On phase-based workflows.** If your process says "each phase updates the runbook", resist mapping phases onto entries. A phase that fixed three defects produces three entries; a phase that fixed none produces zero. **Phase-driven writing is the most reliable way to fill a runbook with diaries.**

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
| **`fi` (on its own, nothing else in the message)** | **Catch-up keyword** — record what the conversation just produced; see below |

> **How it works**: The agent handles intent → selects command → executes CLI. `fixindex` itself stays a deterministic CLI — NL understanding lives in the agent layer, keeping the tool reliable.

Two trigger modes: **explicit keywords** (`Fixindex <question>`, `fi`) when you want control; **implicit triggers** (naming a system + symptom, pasting a log, saying "fixed it") so the agent consults or records automatically without you having to remember.

### Wrap-up writes an entry; `fi` is the catch-up

With a snippet installed, the agent should record an entry **as it wraps up any substantial task** — provided that task actually fixed a defect (if it didn't, it writes nothing; see the section above).

When it misses one, you type two characters:

```
fi
```

A bare `fi` (nothing else in the message) means **record what this conversation just produced, now**. Not "list the entries", not "what would you like me to write" — one clarifying question and the point is lost. The value of `fi` is zero-friction capture at the moment you stop working.

On receiving `fi` the agent should immediately pipe a short summary to
`fixindex fi` — no `list`, no `find`, no clarifying question:

```bash
printf 'SYMPTOM: ...\nROOT: ...\nFIX: ...\nVERIFY: <rerunnable command>' | fixindex fi
```

`fixindex fi` (no args) auto-dedups, appends a new `## §N` to the best-matching
domain file (or creates a new entry if none fits), re-indexes, and commits.
Free text also works (`echo 'one-line symptom' | fixindex fi`). Don't
hand-append `## §N` or edit `symptoms:` yourself.

What goes in is the **root-cause formula, the supporting data, the paths already ruled out, and any portable rule** — not a changelog of what was edited. **Record it even when the fix isn't implemented yet**: say "not fixed", note the next step, and move on. The diagnosis is the asset — it's what saves the next person from re-deriving it.

You can also pipe an entry straight in (the `fi` subcommand reads the body from
stdin and matches the domain for you) — this IS the canonical path now:

```bash
printf 'SYMPTOM: ...\nROOT: ...\nFIX: ...\nVERIFY: <rerunnable command>' | fixindex fi
```

The legacy explicit-domain form `fixindex fi <domain> [--title ... --tags ...]`
still works for pinning an entry to a specific domain.

## Using with LLM coding agents

**One-command snippets for all platforms** in [`agent-snippets/`](./agent-snippets/) — pick your tool (Claude / Codex / Cursor / Gemini / opencode / generic), `cat … >> <rules-file>` to install.

Full natural-language dispatch table (with examples and rationale) in [`docs/agent-integration.md`](./docs/agent-integration.md).

If your agent supports lifecycle hooks, see **Mode C — the three-point loop** in the same doc: a plan-start sweep (auto `fixindex insights "<plan title>"` pull + domain-level find)+ an on-failure lookup right before any retry, and a stop-time gate that blocks wrap-up until the session's fix is recorded. Prompt-based triggers get forgotten under load; hooks don't. The authoritative reference implementation lives in this repo's [`hooks/`](./hooks) (`plan-path-notice.js`, `fi-reminder.sh`); Ether-prompt ships only a deployment copy.

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
