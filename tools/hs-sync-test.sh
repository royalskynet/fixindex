#!/usr/bin/env bash
# hs-sync-test.sh — hs-sync.sh --dry-run --all 的行為測試。
#
# 在 mktemp 目錄造 3 個假條目（active／superseded／stale）加一個 .template.md，
# 跑 --dry-run --all 後斷言：剛好 1 行 RETAIN、2 行 DELETE，模板不出現。
# 全過最後一行印 PASS（exit 0），否則印 FAIL 細節並 exit 1。
#
# 只跑 --dry-run：不打任何真實 API。
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYNC="$SCRIPT_DIR/hs-sync.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/hssync.XXXXXX")"
[ -n "$WORK" ] && [ -d "$WORK" ] || { echo "mktemp failed" >&2; exit 1; }
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/fixes"

if [ ! -f "$SYNC" ]; then
    echo "FAIL: 找不到 $SYNC" >&2
    exit 1
fi

mkfix() {  # mkfix <檔名> <id 欄位值> <status>
    cat > "$WORK/fixes/$1" <<EOF
---
id: $2
slug: sample
title: Sample Entry
status: $3
---

# $1 test

Body of $1.
EOF
}

mkfix "0001-active.md" "1" active
mkfix "0002-superseded.md" "2" superseded
mkfix "0003-stale.md" '"3"' stale

# 模板檔名不是「數字-」開頭，就算 frontmatter 完整也必須被跳過。
cat > "$WORK/fixes/.template.md" <<'EOF'
---
id: 999
slug: template
title: Template
status: active
---

# template
EOF

OUT="$(bash "$SYNC" --dry-run --all "$WORK/fixes" 2>"$WORK/stderr.txt")"
RC=$?

pass=0
fail=0
chk() {  # chk <名稱> <期望> <實際>
    if [ "$2" = "$3" ]; then
        echo "  PASS $1"
        pass=$((pass + 1))
    else
        echo "  FAIL $1 — 期望[$2] 實際[$3]"
        fail=$((fail + 1))
    fi
}

lines="$(printf '%s\n' "$OUT" | grep -c . || true)"
retains="$(printf '%s\n' "$OUT" | grep -c '^RETAIN ' || true)"
deletes="$(printf '%s\n' "$OUT" | grep -c '^DELETE ' || true)"

echo "T1 --dry-run --all 的產出"
chk "hs-sync 本身 exit 0" "0" "$RC"
chk "剛好 3 行輸出" "3" "$lines"
chk "1 行 RETAIN" "1" "$retains"
chk "2 行 DELETE" "2" "$deletes"

echo "T2 每檔動作正確（id: \"3\" 要去引號）"
chk "active → RETAIN 1" "1" "$(printf '%s\n' "$OUT" | grep -cx 'RETAIN 1' || true)"
chk "superseded → DELETE 2" "1" "$(printf '%s\n' "$OUT" | grep -cx 'DELETE 2' || true)"
chk "stale → DELETE 3" "1" "$(printf '%s\n' "$OUT" | grep -cx 'DELETE 3' || true)"

echo "T3 非「數字-」開頭的模板檔必須跳過"
chk "模板 id 未出現" "0" "$(printf '%s\n' "$OUT" | grep -c '999' || true)"
chk "模板名未出現" "0" "$(printf '%s\n' "$OUT" | grep -ci 'template' || true)"

echo "===="
if [ "$fail" -ne 0 ]; then
    echo "FAIL: $fail 項未過（--dry-run 實際輸出：${OUT:-<空>}）"
    [ -s "$WORK/stderr.txt" ] && echo "stderr: $(cat "$WORK/stderr.txt")"
    exit 1
fi
echo "PASS"