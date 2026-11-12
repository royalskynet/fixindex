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
{"type":"assistant","message":{"content":[{"type":"text","text":"dcq_busy_test 斷言修好了，OmniRoute 與 Presidio 正常，Alice 回覆了，ref_9911"}]}}
EOF

# 假 scrub：錢包、姓名換佔位符，並模擬 Presidio 把技術詞誤標 PERSON；mapping 帶原值；/health 回 200
cat > "$T/scrub.py" <<'PY'
import json, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        hits = {"John Smith": "<PERSON_1>", "dcq_busy_test": "<PERSON_2>", "OmniRoute": "<PERSON_3>",
                "Presidio": "<PERSON_4>", "Alice": "<PERSON_5>", "ref_9911": "<CREDIT_CARD_1>"}
        mp, out = {}, []
        for t in body["texts"]:
            for m in re.findall(r"0x[0-9a-fA-F]{40}", t):
                mp["<WALLET_ADDRESS_1>"] = m; t = t.replace(m, "<WALLET_ADDRESS_1>")
            for k, ph in hits.items():
                if k in t:
                    mp[ph] = k; t = t.replace(k, ph)
            out.append(t)
        b = json.dumps({"texts": out, "mapping": mp, "count": len(mp)}).encode()
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
chk "part 不含單名" "$(grep -c 'Alice' "$W"/part.*.txt)" "0"
chk "誤遮還原：識別字" "$(grep -c 'dcq_busy_test' "$W"/part.*.txt)" "1"
chk "誤遮還原：CamelCase" "$(grep -c 'OmniRoute' "$W"/part.*.txt)" "1"
chk "誤遮還原：白名單" "$(grep -c 'Presidio' "$W"/part.*.txt)" "1"
chk "硬類別不還原" "$(grep -c 'ref_9911' "$W"/part.*.txt)" "0"
chk "未脫敏中間檔已刪" "$(ls "$W"/raw.txt "$W"/masked.txt 2>/dev/null | wc -l | tr -d ' ')" "0"
chk "工單列出 part 路徑" "$(grep -c "$W/part.01.txt" "$task")" "1"
chk "工單含報告路徑" "$(grep -c "$W/report.md" "$task")" "2"
chk "工單有驗收段" "$(grep -cx '## 驗收' "$task")" "1"

# 1b. 驗收段：引用必須逐字出現在 part 檔與條目（假 fixindex：show 印 $T/entry，status 回 0）
mkdir -p "$T/bin"
printf '#!/bin/sh\n[ "$1" = show ] && cat "%s/entry"\nexit 0\n' "$T" > "$T/bin/fixindex"; chmod +x "$T/bin/fixindex"
awk '/^```bash$/{f=1;next} /^```$/{f=0} f' "$task" > "$T/accept.sh"
Q='dcq_busy_test 斷言修好了'
rep() { { printf '## 新增\n- 12345 測試條目\n'; [ -n "$1" ] && printf '  原文：%s\n' "$1"; printf '## 補充既有\n## 略過\n## status\n{}\n'; } > "$W/report.md"; }
# 同輪去重檢查讀真實條目檔，所以假 store 也要有對應的 md（與假 fixindex show 同一個 id）
mkdir -p "$T/fixes"
printf -- '---\nid: 12345\ntitle: 測試條目\n---\n\n## §1 Symptom\n\n內文\n' > "$T/fixes/12345-test.md"
acc() { PATH="$T/bin:$PATH" FIXINDEX_DIR="$T/fixes" bash "$T/accept.sh" >/dev/null 2>&1 && echo 0 || echo 1; }
printf 'SYMPTOM: 原文：%s\n' "$Q" > "$T/entry"
rep "$Q"; chk "引用在逐字稿與條目 → 過" "$(acc)" "0"
rep "";   chk "缺原文 → 擋" "$(acc)" "1"
rep "collection 只出現 5 分鐘之後就不見"; printf 'SYMPTOM: collection 只出現 5 分鐘之後就不見\n' > "$T/entry"
chk "杜撰引用（不在逐字稿）→ 擋" "$(acc)" "1"
printf 'SYMPTOM: 改寫過的症狀\n' > "$T/entry"; rep "$Q"
chk "條目沒放引用 → 擋" "$(acc)" "1"
rep "斷言修好了"; printf 'SYMPTOM: 斷言修好了\n' > "$T/entry"
chk "引用太短 → 擋" "$(acc)" "1"

# 1c. 同輪去重：一輪寫兩條同主題（2026-11-12 一輪 17 條只有 6 個主題），驗收要擋
printf -- '---\nid: 12346\ntitle: 測試條目\n---\n\n## §1 Symptom\n\n內文\n' > "$T/fixes/12346-test.md"
printf 'SYMPTOM: 原文：%s\n' "$Q" > "$T/entry"
{ printf '## 新增\n- 12345 測試條目\n  原文：%s\n- 12346 測試條目\n  原文：%s\n' "$Q" "$Q"
  printf '## 補充既有\n## 略過\n## status\n{}\n'; } > "$W/report.md"
chk "同輪同主題兩條 → 擋" "$(acc)" "1"
printf -- '---\nid: 12346\ntitle: 完全無關的另一個根因 launchctl 服務目標\n---\n\n## §1 Symptom\n\n內文\n' > "$T/fixes/12346-test.md"
chk "同輪不同主題兩條 → 過" "$(acc)" "0"
rm -f "$T/fixes/12346-test.md"

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
