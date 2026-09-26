#!/bin/bash
# test_install_commands.sh — install.sh must install /fi, not just the CLI.
# Regression: /fi went missing on every fresh machine and in isolated
# CLAUDE_CONFIG_DIRs (fix 9191) because install.sh only linked the binary.
# Run: bash test_install_commands.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
t="$(mktemp -d "${TMPDIR:-/tmp}/fxinstall.XXXXXX")"; trap 'rm -rf "$t"' EXIT
mkdir -p "$t/home/.claude" "$t/iso"
fail=0
HOME="$t/home" CLAUDE_CONFIG_DIR= FIXINDEX_CLAUDE_DIRS="$t/iso:$t/absent" \
  bash "$here/install.sh" "$t/bin" >"$t/out" 2>&1 || { echo "FAIL install.sh rc!=0"; cat "$t/out"; exit 1; }
for f in "$t/bin/fixindex" "$t/home/.claude/commands/fi.md" "$t/iso/commands/fi.md"; do
  [ -e "$f" ] || { echo "FAIL missing $f"; fail=1; }
done
[ -e "$t/absent" ] && { echo "FAIL created config dir that did not exist"; fail=1; }
cmp -s "$t/home/.claude/commands/fi.md" "$here/commands/fi.md" || { echo "FAIL fi.md content differs"; fail=1; }
# fixindex status must warn (not error) when /fi is missing
mkdir -p "$t/bare/.claude"
w="$(cd "$here" && CLAUDE_CONFIG_DIR="$t/bare/.claude" python3 -c 'import fxstatus;print(fxstatus.commands_state()["warnings"])')"
grep -q 'fi.md' <<<"$w" || { echo "FAIL status did not warn on missing /fi: $w"; fail=1; }
w2="$(cd "$here" && CLAUDE_CONFIG_DIR="$t/home/.claude" python3 -c 'import fxstatus;print(fxstatus.commands_state()["warnings"])')"
[ "$w2" = "[]" ] || { echo "FAIL status warned though /fi installed: $w2"; fail=1; }
[ $fail -eq 0 ] && echo "PASS install-commands (CLI + /fi linked, status guard ok)"
exit $fail
