#!/usr/bin/env bash
# test_defect_reminder_once.sh — fi-reminder.sh「疑似修過 defect 未記」只提醒一次
#
# 為什麼測這個：hook 每次 Stop 都重掃整份 transcript，條件成立後就永遠成立；
# stop_hook_active 只擋同一輪，所以沒有「已提醒」記號時每則使用者訊息都會再擋一次
# （2026-10-26 m2 實測連續 6 輪）。拿掉 defect-reminded 記號，第 2 項會 fail。

set -u
H="${FI_REMINDER_HOOK:-$(cd "$(dirname "$0")" && pwd)/hooks/fi-reminder.sh}"
D=$(mktemp -d)
export HOME="$D/home"   # 記號檔寫進臨時 HOME，不污染生產 guard-state
mkdir -p "$HOME"
trap 'rm -rf "$D"' EXIT

# 追加 $2 次「改 js」tool_use（第一次呼叫另附修復語意文字）
add_edits() {
  local f="$1" n="$2" i
  for ((i=0;i<n;i++)); do
    echo '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/Users/x/dev/app.js","content":"x"}}]}}' >> "$f"
  done
}
run() { echo "{\"transcript_path\":\"$1\",\"stop_hook_active\":false}" | bash "$H" 2>/dev/null; }
is_block() { printf '%s' "$1" | grep -q '"decision": "block"' && echo yes || echo no; }

fail=0
chk() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want=$2 got=$3"; fail=1; fi; }

f=$D/abcd1234-test.jsonl
add_edits "$f" 45
echo '{"type":"assistant","message":{"content":[{"type":"text","text":"已定位根因並修復"}]}}' >> "$f"

chk "1 首次符合條件要提醒"            yes "$(is_block "$(run "$f")")"
chk "2 同 transcript 再跑不再提醒"     no  "$(is_block "$(run "$f")")"
add_edits "$f" 1
chk "3 有新改檔才再提醒"              yes "$(is_block "$(run "$f")")"
chk "4 提醒後再跑又不提醒"            no  "$(is_block "$(run "$f")")"

[ "$fail" -eq 0 ] && echo "ALL PASS" || { echo "FAILED"; exit 1; }
