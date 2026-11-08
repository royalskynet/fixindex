#!/usr/bin/env bash
# fi-deep.sh 測試：正常產工單、PII 不出現在 part 檔、scrub 不通 fail-closed、lint FAIL、缺 transcript。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
FD="$HERE/fi-deep.sh"
T="$(mktemp -d)"
fail=0
chk() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: got '$2' want '$3'"; fail=1; fi; }

WALLET="0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
cat > "$T/s.jsonl" <<EOF
{"type":"user","message":{"content":"轉帳到 ${WALLET}，聯絡 John Smith"}}
{"type":"assistant","message":{"content":[{"type":"text","text":"dcq_busy_test 斷言修好了"}]}}
EOF

# 假 scrub：錢包與姓名換佔位符；/health 回 200
cat > "$T/scrub.py" <<'PY'
import json, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = [re.sub(r"0x[0-9a-fA-F]{40}", "<WALLET_ADDRESS_1>", t).replace("John Smith", "<PERSON_1>") for t in body["texts"]]
        b = json.dumps({"texts": out, "mapping": {}, "count": 2}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
s = HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[1], "w").write(str(s.server_port))
s.serve_forever()
PY
python3 "$T/scrub.py" "$T/port" & SP=$!
trap 'kill $SP 2>/dev/null; rm -rf "$T"' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$T/port" ] && break; sleep 0.3; done
URL="http://127.0.0.1:$(cat "$T/port")"

printf '#!/bin/sh\necho "LINT OK"\n' > "$T/lint-ok"; chmod +x "$T/lint-ok"
printf '#!/bin/sh\necho "LINT FAIL: 測試"\nexit 1\n' > "$T/lint-fail"; chmod +x "$T/lint-fail"

run() { TMPDIR="$T/tmp" FI_TASK_DIR="$T/tasks" FI_SCRUB_URL="$1" FI_DEEP_LINT="$2" bash "$FD" "${3:-$T/s.jsonl}" >"$T/out" 2>"$T/err"; }
mkdir -p "$T/tmp"

# 1. 正常
if run "$URL" "$T/lint-ok"; then rc=0; else rc=$?; fi
chk "正常 rc" "$rc" "0"
last="$(tail -n 1 "$T/out")"
chk "最後一行是 deep-run 指令" "$(printf '%s' "$last" | cut -d' ' -f1)" "deep-run"
task="$(printf '%s' "$last" | cut -d' ' -f2)"
chk "工單存在" "$([ -s "$task" ] && echo y)" "y"
W="$(ls -d "$T/tmp"/fi-deep-* | head -1)"
chk "part 檔存在" "$(ls "$W"/part.*.txt 2>/dev/null | wc -l | tr -d ' ')" "1"
chk "part 不含錢包" "$(grep -c "$WALLET" "$W"/part.*.txt)" "0"
chk "part 不含姓名" "$(grep -c 'John Smith' "$W"/part.*.txt)" "0"
chk "part 保留技術詞" "$(grep -c 'dcq_busy_test' "$W"/part.*.txt)" "1"
chk "未脫敏中間檔已刪" "$(ls "$W"/raw.txt "$W"/masked.txt 2>/dev/null | wc -l | tr -d ' ')" "0"
chk "工單列出 part 路徑" "$(grep -c "$W/part.01.txt" "$task")" "1"
chk "工單含報告路徑" "$(grep -c "$W/report.md" "$task")" "2"
chk "工單有驗收段" "$(grep -cx '## 驗收' "$task")" "1"

# 2. scrub 不通：fail-closed，不留工單與工作目錄
rm -rf "$T/tmp" "$T/tasks"; mkdir -p "$T/tmp"
if run "http://127.0.0.1:9" "$T/lint-ok"; then rc=0; else rc=$?; fi
chk "scrub 不通 rc" "$rc" "3"
chk "scrub 不通不產工單" "$(ls "$T/tasks" 2>/dev/null | wc -l | tr -d ' ')" "0"
chk "scrub 不通不留工作目錄" "$(ls "$T/tmp" | wc -l | tr -d ' ')" "0"

# 3. lint FAIL
rm -rf "$T/tmp"; mkdir -p "$T/tmp"
if run "$URL" "$T/lint-fail"; then rc=0; else rc=$?; fi
chk "lint FAIL rc" "$rc" "4"

# 4. 缺 transcript
if run "$URL" "$T/lint-ok" "$T/none.jsonl"; then rc=0; else rc=$?; fi
chk "缺 transcript rc" "$rc" "2"

exit "$fail"
