#!/usr/bin/env bash
# fi_pipeline.py 測試：假 LLM（FI_ASK_CMD）＋假 fixindex，驗六段流程與 fail-closed。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PIPE="$HERE/fi_pipeline.py"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
fail=0
chk() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: got '$2' want '$3'"; fail=1; fi; }

Q0='Error: proxy on :3200 was killed by dc-restart'
Q3='使用者說：同一輪寫出去的條目自己也看不到'
Q4='dc-restart 把各 session 的 proxy 當洩漏殺掉了'

# 假 LLM：照 ds-run.sh --ask 的介面（<W> --ask "<問題>"），答案寫 <W>/task/notes.md
cat > "$T/ask" <<'PY'
#!/usr/bin/env python3
import os, sys, json, shutil
w, flag, q = sys.argv[1], sys.argv[2], sys.argv[3]
assert flag == '--ask'
log = os.environ['FAKE_LOG']
open(log, 'a').write(('extract' if 'STAGE=extract' in q else 'adjudicate' if 'STAGE=adjudicate' in q else 'other') + '\n')
if 'STAGE=extract' in q and os.environ.get('FAKE_SLEEP'):
    import time; time.sleep(float(os.environ['FAKE_SLEEP']))
if os.environ.get('FAKE_ASK_FAIL'):
    print('FAIL worker'); sys.exit(4)
os.makedirs(os.path.join(w, 'task'), exist_ok=True)
out = open(os.path.join(w, 'task', 'notes.md'), 'w')
Q0, Q3, Q4 = os.environ['Q0'], os.environ['Q3'], os.environ['Q4']
if 'STAGE=extract' in q:
    part_files = [f for f in os.listdir(w) if f.startswith('part.')]
    part_text = open(os.path.join(w, part_files[0]), encoding='utf-8').read() if part_files else ''
    if os.environ.get('FAKE_NONE') or Q0 not in part_text:
        out.write('NONE\n'); sys.exit(0)
    sym = lambda core, qq, quote, rule=True: json.dumps({'kind': 'symptom', 'core': core, 'query': qq, 'quote': quote,
        'fields': dict({'SYMPTOM': core, 'ROOT': 'r', 'FIX': 'f', 'VERIFY': 'v'}, **({'RULE': 'rule ' + core} if rule else {}))}, ensure_ascii=False)
    out.write('以下是候選：\n')
    out.write(sym('C0 dc-restart 殺掉 proxy', 'dc-restart proxy', Q0) + '\n')
    out.write(sym('C1 杜撰引用', 'fake', '這句完全不存在於逐字稿裡面的引用') + '\n')
    out.write(sym('C2 缺規則', 'norule', Q4, rule=False) + '\n')
    out.write(json.dumps({'kind': 'insight', 'core': 'C3 同輪看不到自己', 'query': '同輪 重複', 'quote': Q3,
        'fields': {'CONTEXT': '原文：' + Q3, 'INSIGHT': 'i', 'IMPLICATION': 'm', 'QUERIES': 'q', 'RULE': 'rule C3'}}, ensure_ascii=False) + '\n')
    out.write('{not json\n')
    out.write(sym('C4 proxy 被當洩漏', 'proxy 洩漏', Q4) + '\n')
    for n in range(int(os.environ.get('FAKE_MANY') or 0)):
        out.write(sym('M%d 多條' % n, 'proxy 多條 %d' % n, Q0) + '\n')
elif 'STAGE=adjudicate' in q:
    inp = os.path.join(w, 'adjudicate.json')
    assert 'adjudicate.json' in q, 'adjudicate question must name the input file'
    shutil.copy(inp, os.path.join(w, 'seen-adjudicate.json'))
    mode = os.environ.get('FAKE_ADJ_MISSING', '')
    prior = open(log).read().count('adjudicate') if os.path.exists(log) else 0
    omit4 = mode == 'always' or (mode == 'once' and prior <= 1)
    rows = ['{"i":"0","action":"write"}', '{"i":1,"action":"write"}', '{"i":3,"action":"write"}']
    if not omit4:
        rows.append('{"i":4,"action":"skip","reason":"同輪重複，併入 0"}')
    out.write('```\n' + '\n'.join(rows) + '\n```\n')
PY
chmod +x "$T/ask"

# 假 fixindex：find/insights 回多 query JSON、fi 記 stdin、status 回 ok
mkdir -p "$T/bin"
cat > "$T/bin/fixindex" <<'PY'
#!/usr/bin/env python3
import os, sys, json
log = os.environ['FAKE_LOG']
a = sys.argv[1:]
open(log, 'a').write('fixindex ' + ' '.join(a) + '\n')
if a and a[0] in ('find', 'insights'):
    qs = []
    if '--queries-file' in a:
        qs = [l.strip() for l in open(a[a.index('--queries-file') + 1]) if l.strip()]
    hits = lambda q: [{'key': '0555#1', 'file': '0555-proxy.md', 'title': '既有 proxy 條目', 'score': 1.2}] \
        if 'proxy' in q and a[0] == 'find' else []
    print(json.dumps({'queries': [{'query': q, 'hits': hits(q)} for q in qs]}, ensure_ascii=False))
elif a and a[0] == 'fi':
    d = os.environ['FAKE_DIR']
    data = sys.stdin.read()
    n = len([x for x in os.listdir(d) if x.startswith('fi-in-')]) + 1
    open(os.path.join(d, f'fi-in-{n}'), 'w').write(data)
    print('[fixindex] wrote')
    if n == 1:
        print(json.dumps({'created': os.path.join(d, 'fixes', '9101-x.md'), 'dedup': False}))
    else:
        print(json.dumps({'appended': '0777-y.md', 'section': 3}))
elif a and a[0] == 'status':
    print('{"ok": true}')
PY
chmod +x "$T/bin/fixindex"

setup() {  # $1 = case dir
  rm -rf "$1"; mkdir -p "$1/W" "$1/d"
  printf '%s\n' "雜訊一行" "$Q0" "$Q3" "中間" "$Q4" > "$1/W/part.01.txt"
}
runp() {  # $1 = case dir, rest = extra env
  local c="$1"; shift
  env "$@" PATH="$T/bin:$PATH" FI_ASK_CMD="$T/ask" FAKE_LOG="$c/log" FAKE_DIR="$c/d" Q0="$Q0" Q3="$Q3" Q4="$Q4" \
    python3 "$PIPE" "$c/W" >"$c/out" 2>"$c/err"
}

# 1. 正常流程
C="$T/c1"; setup "$C"
if runp "$C"; then rc=0; else rc=$?; fi
chk "正常 rc" "$rc" "0"
chk "LLM 只叫兩次（抽＋裁）" "$(tr '\n' ' ' < "$C/log" | grep -o 'extract\|adjudicate' | tr '\n' ' ')" "extract adjudicate "
chk "find 只跑一次" "$(grep -c '^fixindex find ' "$C/log")" "1"
chk "insights 只跑一次" "$(grep -c '^fixindex insights ' "$C/log")" "1"
chk "find 用 --queries-file --json" "$(grep '^fixindex find ' "$C/log" | grep -q -- '--queries-file' && grep '^fixindex find ' "$C/log" | grep -q -- '--json' && echo y)" "y"
chk "queries.txt 只含通過過濾的 3 條" "$(grep -c . "$C/W/queries.txt" 2>/dev/null)" "3"
chk "裁決輸入只含 i=0,3,4" "$(python3 -c 'import json,sys; print(sorted(c["i"] for c in json.load(open(sys.argv[1]))))' "$C/W/ask.adjudicate/seen-adjudicate.json" 2>/dev/null)" "[0, 3, 4]"
chk "查重結果附在候選上" "$(python3 -c 'import json,sys; d={c["i"]:c for c in json.load(open(sys.argv[1]))}; print(d[0]["hits"][0]["key"])' "$C/W/ask.adjudicate/seen-adjudicate.json" 2>/dev/null)" "0555#1"
chk "fixindex fi 呼叫 2 次" "$(ls "$C/d"/fi-in-* 2>/dev/null | wc -l | tr -d ' ')" "2"
chk "第 1 筆是 C0" "$(grep -q 'C0' "$C/d/fi-in-1" 2>/dev/null && echo y)" "y"
chk "C0 的 SYMPTOM 補上原文引用" "$(grep '^SYMPTOM:' "$C/d/fi-in-1" 2>/dev/null | grep -qF "原文：$Q0" && echo y)" "y"
chk "C0 帶 RULE" "$(grep -q '^RULE: ' "$C/d/fi-in-1" 2>/dev/null && echo y)" "y"
chk "第 2 筆是 C3 insight" "$(grep -q '^CONTEXT:' "$C/d/fi-in-2" 2>/dev/null && grep -q 'C3\|rule C3' "$C/d/fi-in-2" && echo y)" "y"
chk "C3 的引用不重複補" "$(grep -oF "$Q3" "$C/d/fi-in-2" 2>/dev/null | wc -l | tr -d ' ')" "1"
chk "被過濾的 C1 沒寫（裁決說 write 也不寫）" "$(grep -l 'C1' "$C/d"/fi-in-* 2>/dev/null | wc -l | tr -d ' ')" "0"
R="$C/W/report.md"
for h in '## 新增' '## 補充既有' '## 略過' '## status'; do chk "報告有 $h" "$(grep -qxF "$h" "$R" 2>/dev/null && echo y)" "y"; done
chk "新增列 9101＋原文" "$(awk '/^## 新增$/{f=1;next} /^## /{f=0} f' "$R" | grep -A1 '^- 9101 ' | grep -cF "  原文：$Q0")" "1"
chk "補充既有列 0777＋原文" "$(awk '/^## 補充既有$/{f=1;next} /^## /{f=0} f' "$R" | grep -A1 '^- 0777 ' | grep -cF "  原文：$Q3")" "1"
chk "略過 3 條" "$(awk '/^## 略過$/{f=1;next} /^## /{f=0} f' "$R" | grep -c '^- ')" "3"
chk "略過寫出 C1 原因" "$(grep -q '^- C1 杜撰引用 — 引用不在逐字稿' "$R" && echo y)" "y"
chk "略過寫出 C2 原因" "$(grep -q '^- C2 缺規則 — 缺 RULE' "$R" && echo y)" "y"
chk "略過寫出 C4 原因" "$(grep -q '^- C4 proxy 被當洩漏 — 同輪重複，併入 0' "$R" && echo y)" "y"
chk "status 段是 status 原始輸出" "$(awk '/^## status$/{f=1;next} f' "$R" | grep -c '"ok": true')" "1"

# 2. LLM 失敗：fail-closed，不寫任何條目
C="$T/c2"; setup "$C"
if runp "$C" FAKE_ASK_FAIL=1; then rc=0; else rc=$?; fi
chk "LLM 失敗 rc≠0" "$([ "$rc" -ne 0 ] && echo y)" "y"
chk "LLM 失敗不寫 fixindex" "$(ls "$C/d"/fi-in-* 2>/dev/null | wc -l | tr -d ' ')" "0"

# 3. 沒有候選：報告寫「- 無」、不裁決、不寫
C="$T/c3"; setup "$C"
if runp "$C" FAKE_NONE=1; then rc=0; else rc=$?; fi
chk "無候選 rc" "$rc" "0"
chk "無候選不叫裁決" "$(grep -c adjudicate "$C/log")" "0"
chk "無候選不寫 fixindex" "$(ls "$C/d"/fi-in-* 2>/dev/null | wc -l | tr -d ' ')" "0"
chk "無候選報告寫 - 無" "$(awk '/^## 新增$/{f=1;next} /^## /{f=0} f' "$C/W/report.md" 2>/dev/null | grep -cx -- '- 無')" "1"

# 4. 多塊：每塊各抽一次；成功後前移標記
C="$T/c4"; setup "$C"; printf '%s\n' "第二塊沒有候選" > "$C/W/part.02.txt"
printf '%s\t42\n' "$C/state/sid" > "$C/W/mark"
if runp "$C"; then rc=0; else rc=$?; fi
chk "多塊 rc" "$rc" "0"
chk "多塊各抽一次" "$(grep -c '^extract' "$C/log")" "2"
chk "成功後前移標記" "$(cat "$C/state/sid" 2>/dev/null)" "42"

# 5. LLM 失敗不前移標記
C="$T/c5"; setup "$C"; printf '%s\t42\n' "$C/state/sid" > "$C/W/mark"
runp "$C" FAKE_ASK_FAIL=1 || true
chk "失敗不前移標記" "$([ -e "$C/state/sid" ] && echo y)" ""

# 6. 各塊平行抽：3 塊各睡 2 秒，總耗時要小於依序的 6 秒
C="$T/c6"; setup "$C"; printf '%s\n' "x" > "$C/W/part.02.txt"; printf '%s\n' "y" > "$C/W/part.03.txt"
s=$(date +%s); runp "$C" FAKE_SLEEP=2 || true
chk "三塊平行抽 <5s" "$([ $(( $(date +%s) - s )) -lt 5 ] && echo y)" "y"

# 7. 超過時限：rc=6，不寫入、不前移標記
C="$T/c7"; setup "$C"; printf '%s\t42\n' "$C/state/sid" > "$C/W/mark"
if runp "$C" FI_DEADLINE_AT=1; then rc=0; else rc=$?; fi
chk "超時 rc=6" "$rc" "6"
chk "超時不寫入" "$(grep -cx 'fixindex fi' "$C/log")" "0"
chk "未超時才寫入（對照）" "$([ "$(grep -cx 'fixindex fi' "$T/c1/log")" -gt 0 ] && echo y)" "y"
chk "超時不前移標記" "$([ -e "$C/state/sid" ] && echo y)" ""

# 8. LLM 段來得及、寫入前剩不到 10 秒：停止寫入、rc=6、不前移標記
C="$T/c8"; setup "$C"; printf '%s\t42\n' "$C/state/sid" > "$C/W/mark"
if runp "$C" FI_DEADLINE_AT=$(( $(date +%s) + 5 )) FI_RESERVE=-60; then rc=0; else rc=$?; fi
chk "寫入前時限不足 rc=6" "$rc" "6"
chk "寫入前時限不足不寫" "$(grep -cx 'fixindex fi' "$C/log")" "0"
chk "寫入前時限不足不前移標記" "$([ -e "$C/state/sid" ] && echo y)" ""

# 9. queries 多（3＋6 條）：find 分 3 組平行，查重結果仍附回每個候選
C="$T/c9"; setup "$C"
runp "$C" FAKE_MANY=6 || true
chk "find 分組" "$(grep -c '^fixindex find ' "$C/log")" "3"
chk "分組後 hits 合回" "$(python3 -c 'import json,sys; print(sum(1 for c in json.load(open(sys.argv[1])) if c["hits"]))' "$C/W/ask.adjudicate/seen-adjudicate.json" 2>/dev/null)" "8"

# 10. 裁決漏一個 id：重問一次後補齊，正常寫入
C="$T/c10"; setup "$C"
if runp "$C" FAKE_ADJ_MISSING=once; then rc=0; else rc=$?; fi
chk "裁決漏 id 重問後 rc" "$rc" "0"
chk "裁決漏 id 會重問" "$(grep -c '^adjudicate' "$C/log")" "2"
chk "重問補齊後仍寫 2 筆" "$(ls "$C/d"/fi-in-* 2>/dev/null | wc -l | tr -d ' ')" "2"

# 11. 裁決一直漏 id：fail-closed，不寫任何條件、不前移標記
C="$T/c11"; setup "$C"; printf '%s	42
' "$C/state/sid" > "$C/W/mark"
if runp "$C" FAKE_ADJ_MISSING=always; then rc=0; else rc=$?; fi
chk "裁決持續漏 id rc=3" "$rc" "3"
chk "裁決持續漏 id 不寫 fixindex" "$(ls "$C/d"/fi-in-* 2>/dev/null | wc -l | tr -d ' ')" "0"
chk "裁決持續漏 id 不前移標記" "$([ -e "$C/state/sid" ] && echo y)" ""
chk "裁決持續漏 id stderr 明說" "$(grep -c '裁決仍漏候選 id' "$C/err")" "1"

exit $fail
