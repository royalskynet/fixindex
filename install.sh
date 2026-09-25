#!/usr/bin/env bash
# install.sh — symlink fixindex into ~/.local/bin (or a user-supplied dir), and
# the bundled slash commands (commands/*.md, e.g. /fi) into the Claude Code
# config dir. The CLI alone is not a full install: without commands/fi.md every
# fresh machine / isolated CLAUDE_CONFIG_DIR silently loses /fi.
set -euo pipefail

TARGET_DIR="${1:-$HOME/.local/bin}"
REPO="$(cd "$(dirname "$0")" && pwd)"
SRC="$REPO/fixindex"

mkdir -p "$TARGET_DIR"
ln -sf "$SRC" "$TARGET_DIR/fixindex"
echo "Linked $TARGET_DIR/fixindex -> $SRC"

# Claude Code slash commands. Honors CLAUDE_CONFIG_DIR (isolated configs such as
# deepclaude); extra config dirs can be listed in FIXINDEX_CLAUDE_DIRS (':'-separated).
CLAUDE_DIRS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}${FIXINDEX_CLAUDE_DIRS:+:$FIXINDEX_CLAUDE_DIRS}"
IFS=':' read -r -a dirs <<<"$CLAUDE_DIRS"
for cdir in "${dirs[@]}"; do
  [ -n "$cdir" ] || continue
  if [ ! -d "$cdir" ]; then
    echo "Skip slash commands: $cdir not found (Claude Code not installed there)"
    continue
  fi
  mkdir -p "$cdir/commands"
  for cmd in "$REPO"/commands/*.md; do
    ln -sf "$cmd" "$cdir/commands/$(basename "$cmd")"
    echo "Linked $cdir/commands/$(basename "$cmd") -> $cmd"
  done
done

echo ""
echo "Ensure $TARGET_DIR is on your PATH. For zsh:"
echo "  echo 'export PATH=\"$TARGET_DIR:\$PATH\"' >> ~/.zshrc"
echo ""
echo "Sanity check:"
"$TARGET_DIR/fixindex" help | head -3
