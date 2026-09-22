#!/bin/bash
# test_cwd_probe.sh — fixindex must survive a cwd it cannot write to (fix 0926:
# /bin/bash 3.2 puts heredoc temp files in $PWD). Run: bash test_cwd_probe.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
d="$(mktemp -d "${TMPDIR:-/tmp}/fxprobe.XXXXXX")"; chmod 555 "$d"
trap 'chmod 755 "$d"; rm -rf "$d"' EXIT
if ( cd "$d" && /bin/bash -c 'cat <<X
x
X' ) >/dev/null 2>&1; then echo "SKIP: this bash keeps heredocs off \$PWD"; exit 0; fi
out="$(cd "$d" && "$here/fixindex" fi --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && ! grep -q 'here document' <<<"$out"; then echo "PASS cwd-probe (rc=0, no heredoc error)"; else echo "FAIL rc=$rc"; echo "$out" | head -3; exit 1; fi
