# Agent snippets — drop-in fixindex integration

One copy-paste block per agent platform. Pick the file matching your tool, append (don't replace) it to that tool's global instructions file, restart the agent.

| Agent | Target file | Snippet |
|-------|-------------|---------|
| Claude Code | `~/.claude/CLAUDE.md` or `<repo>/CLAUDE.md` | [claude.md](./claude.md) |
| Codex CLI / GPT agents | `~/.config/codex/AGENTS.md` or `<repo>/AGENTS.md` | [codex.md](./codex.md) |
| Cursor | `<repo>/.cursorrules` | [cursor.md](./cursor.md) |
| Gemini CLI | `~/.gemini/GEMINI.md` or `<repo>/GEMINI.md` | [gemini.md](./gemini.md) |
| opencode | `<repo>/AGENTS.md` | [opencode.md](./opencode.md) |
| Generic / other | any rule file | [generic.md](./generic.md) |

## One-liner install

From the repo root:

```bash
# Claude Code (global)
cat agent-snippets/claude.md >> ~/.claude/CLAUDE.md

# Codex CLI (global)
mkdir -p ~/.config/codex && cat agent-snippets/codex.md >> ~/.config/codex/AGENTS.md

# Cursor (per-repo)
cat agent-snippets/cursor.md >> .cursorrules

# Gemini CLI (global)
mkdir -p ~/.gemini && cat agent-snippets/gemini.md >> ~/.gemini/GEMINI.md
```

All snippets share the same dispatch rules — they differ only in tool-specific framing (CLAUDE.md uses Markdown sections, `.cursorrules` is plain text, etc.). See [`../docs/agent-integration.md`](../docs/agent-integration.md) for the full rationale and Mode A / Mode B reference.
