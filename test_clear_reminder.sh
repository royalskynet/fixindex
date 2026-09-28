#!/usr/bin/env bash
# test_clear_reminder.sh — fi-reminder.sh 長 session OOM 提醒（fix 9696）
#
# 為什麼測這個：Claude Code 的 mutableMessages 永不釋放（claude-code#25926），
# 長 session 會在 V8 Zone 配置器 SIGABRT。門檻算錯 = 提醒不會響 = 防線等於沒有。
# 觸發條件是「牆鐘時長」不是 turn 數；改錯成 turn 數這個測試會 fail。

set -u
H="$(cd "$(dirname "$0")" && pwd)/hooks/fi-reminder.sh"
D=$(mktemp -d)
G=~/.claude/guard-state
mkdir -p "$G"
trap 'rm -rf "$D"' EXIT

# 造一份 3 筆 assistant 的 transcript，頭尾相距 $2 小時
mk() {
  python3 -c "
import json,sys
from datetime import datetime,timedelta,timezone
f,h=sys.argv[1],float(sys.argv[2])
t0=datetime(2026,9,28,10,0,tzinfo=timezone.utc)
with open(f,'w') as o:
    for i in range(3):
        ts=(t0+timedelta(hours=h*i/2)).isoformat().replace('+00:00','Z')
        o.write(json.dumps({'type':'assistant','timestamp':ts,'message':{'content':[]}})+'\n')
" "$1" "$2"
}

run() { echo "{\"transcript_path\":\"$1\",\"stop_hook_active\":false}" | bash "$H" 2>/dev/null; }
mark_of() { echo "$G/clear-reminded-$(basename "$1" | cut -c1-8)"; }

fail=0
chk() {
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want=$2 got=$3"; fail=1; fi
}

# 1) 超過門檻 → 提醒，且訊息要指向 /clear（不是 /compact，compact 不釋放記憶體）
f=$D/a.jsonl; mk "$f" 3; rm -f "$(mark_of "$f")"
o=$(run "$f")
echo "$o" | grep -q "小時" && r=yes || r=no
chk "3h 觸發提醒" yes "$r"
echo "$o" | grep -q -- "/clear" && r=yes || r=no
chk "訊息指向 /clear" yes "$r"
echo "$o" | python3 -c "import json,sys; json.loads(sys.stdin.read().strip() or '{}')" 2>/dev/null && r=ok || r=bad
chk "輸出合法 JSON" ok "$r"

# 2) 同 session 一小時內不重複刷（mark 檔生效）
o=$(run "$f")
echo "$o" | grep -q "小時" && r=yes || r=no
chk "1h 內不重複刷" no "$r"

# 3) 未達門檻 → 靜默
f=$D/b.jsonl; mk "$f" 1; rm -f "$(mark_of "$f")"
o=$(run "$f")
echo "$o" | grep -q "小時" && r=yes || r=no
chk "1h 不觸發" no "$r"

# 4) 舊格式 transcript 沒有 timestamp 欄位 → 不能崩
f=$D/c.jsonl; printf '{"type":"assistant","message":{"content":[]}}\n' > "$f"
run "$f" >/dev/null 2>&1
chk "無 timestamp 不崩" 0 "$?"

exit $fail
