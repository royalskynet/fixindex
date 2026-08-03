# Fix Logs Directory

This directory holds your personal fix logs. By default, `fixindex` reads from `./fixes/` in the current working directory.

**Set `FIXINDEX_DIR` to point to your actual fix log repository:**

```bash
export FIXINDEX_DIR="$HOME/.claude/projects/-Users-51mini/memory/fixes"
export FIXINDEX_INDEX="$HOME/.claude/projects/-Users-51mini/memory/FIX-INDEX.md"
```

The fix logs themselves are versioned in a **separate private repository** (e.g., `fixindex-log`). This public repo contains only the CLI tool.
