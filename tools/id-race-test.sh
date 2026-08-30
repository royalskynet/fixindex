#!/usr/bin/env bash
# id-race-test.sh — next_id 配號競態回歸（0616）
# 兩個 python3 背景行程同時各連續配號+建檔 20 次；
# 40 個 ID 必須全唯一（除非配號鎖失效，否則不該有重複）。
#
# 用法：bash tools/id-race-test.sh
# 輸出：PASS: 40 IDs unique ／ FAIL: 出現重複 ID
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/fxrace.XXXXXX")"
[ -n "$WORK" ] && [ -d "$WORK" ] || { echo "mktemp failed" >&2; exit 1; }
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/fixes"

export FIXINDEX_DIR="$WORK/fixes"
export PYTHONPATH="$REPO_ROOT"

worker() {
  python3 - "$WORK" <<'PY'
import os, sys
sys.path.insert(0, os.environ['PYTHONPATH'])
import fxauto
work = sys.argv[1]
for i in range(20):
    with fxauto.id_lock():
        fid = fxauto.next_id(_locked=False)
        path = os.path.join(work, 'fixes', f'{fid}-race-{os.getpid()}-{i}.md')
        with open(path, 'w') as f:
            f.write('x')
        print(fid)
PY
}

( worker ) > "$WORK/a.txt" &
( worker ) > "$WORK/b.txt" &
wait

total="$(cat "$WORK/a.txt" "$WORK/b.txt" | wc -l | tr -d ' ')"
dups="$(cat "$WORK/a.txt" "$WORK/b.txt" | sort | uniq -d)"

if [ "$total" -ne 40 ]; then
  echo "FAIL: 產出 $total 個 ID（預期 40）"
  exit 1
fi
if [ -n "$dups" ]; then
  echo "FAIL: 重複 ID 出現："
  echo "$dups"
  exit 1
fi
echo "PASS: 40 IDs unique"