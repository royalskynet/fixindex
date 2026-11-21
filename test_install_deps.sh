#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
t="$(mktemp -d)"; trap 'rm -rf "$t"' EXIT
mkdir -p "$t/shim" "$t/home"
printf '#!/bin/sh\nexit 1\n' > "$t/shim/python3"
chmod +x "$t/shim/python3"
if HOME="$t/home" PATH="$t/shim:$PATH" bash "$here/install.sh" "$t/bin" >"$t/out" 2>&1; then
  echo "FAIL: installer accepted missing dependencies"
  exit 1
fi
grep -q 'python3 -m pip install -r' "$t/out"
[[ ! -e "$t/bin" ]]
echo "PASS install-deps (missing dependency stops before linking)"
