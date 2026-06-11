#!/usr/bin/env bash
# install.sh — symlink fixindex into ~/.local/bin or a user-supplied dir.
set -euo pipefail

TARGET_DIR="${1:-$HOME/.local/bin}"
SRC="$(cd "$(dirname "$0")" && pwd)/fixindex"

mkdir -p "$TARGET_DIR"
ln -sf "$SRC" "$TARGET_DIR/fixindex"

echo "Linked $TARGET_DIR/fixindex -> $SRC"
echo ""
echo "Ensure $TARGET_DIR is on your PATH. For zsh:"
echo "  echo 'export PATH=\"$TARGET_DIR:\$PATH\"' >> ~/.zshrc"
echo ""
echo "Sanity check:"
"$TARGET_DIR/fixindex" help | head -3
