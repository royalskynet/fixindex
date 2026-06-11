#!/usr/bin/env bash
# claude-code-userpromptsubmit.sh
#
# Claude Code UserPromptSubmit hook.
# Extracts keywords from the user's message, searches the fixindex runbook,
# and injects any matches as additionalContext so the model can reference them.
#
# Install: add to ~/.claude/settings.json hooks.UserPromptSubmit
# (see docs/claude-code-hook.md for the full snippet)
#
# Env vars (same as fixindex CLI):
#   FIXINDEX_DIR    — path to fixes/ directory (default: ./fixes)
#   FIXINDEX_INDEX  — path to FIX-INDEX.md    (default: ./FIX-INDEX.md)
#   RG              — ripgrep binary           (default: rg)

set -euo pipefail

FIXES_DIR="${FIXINDEX_DIR:-$PWD/fixes}"
RG="${RG:-rg}"

[[ -d "$FIXES_DIR" ]] || exit 0
command -v "$RG" >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
msg=$(printf '%s' "$input" \
  | jq -r '.message // .user_message // .prompt // .content // empty' 2>/dev/null \
  | head -c 400)
[[ -z "$msg" ]] && exit 0

# Extract keywords: CJK 2+ char sequences and ASCII 4+ char words
keywords=$(printf '%s' "$msg" | python3 -c "
import sys, re
text = sys.stdin.read()
cjk   = re.findall(r'[一-鿿]{2,}', text)
ascii = re.findall(r'[a-zA-Z]{4,}', text)
print('\n'.join(cjk + ascii))
" 2>/dev/null)
[[ -z "$keywords" ]] && exit 0

# rg alternation over top 6 keywords
pattern=$(printf '%s' "$keywords" | head -6 | paste -sd '|' -)
[[ -z "$pattern" ]] && exit 0

results=$("$RG" -i --heading --line-number "$pattern" \
  "$FIXES_DIR"/[0-9]*.md 2>/dev/null | head -40)
[[ -z "$results" ]] && exit 0

context=$(printf '[fixindex runbook matches]\n%s' "$results" | jq -Rs .)
printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":%s}}' "$context"
