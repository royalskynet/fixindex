# Claude Code Hook Integration

`hooks/claude-code-userpromptsubmit.sh` wires fixindex into Claude Code as a
`UserPromptSubmit` hook. Every time you send a message, it extracts keywords,
searches your runbook, and injects any matches as `additionalContext` — the
model sees them and can reference them without being explicitly asked.

## Requirements

- Claude Code ≥ 1.x
- `jq`
- `ripgrep` (`rg`)
- `python3` (stdlib only)

## Setup

**1. Set env vars** (add to `~/.zshrc` or `~/.bashrc`):

```bash
export FIXINDEX_DIR="$HOME/fixindex/fixes"
export FIXINDEX_INDEX="$HOME/fixindex/FIX-INDEX.md"
```

**2. Add to `~/.claude/settings.json`**:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$HOME/fixindex/hooks/claude-code-userpromptsubmit.sh\"",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Merge with any existing `hooks` — don't replace the whole block.

## How it works

1. Receives the user message as JSON on stdin
2. Extracts CJK 2-char+ sequences and ASCII 4-char+ words as keywords
3. Runs `rg` alternation search over `$FIXINDEX_DIR/*.md`
4. If hits found, returns `additionalContext` with the matching lines
5. Claude sees the runbook excerpt and can apply the fix without being asked

## Test

```bash
echo '{"message":"server hang spawnSync timeout"}' \
  | bash hooks/claude-code-userpromptsubmit.sh
```

Expected: JSON with `hookSpecificOutput.additionalContext` containing matched lines,
or empty output if no matches.
