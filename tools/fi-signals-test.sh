#!/usr/bin/env bash
# fi-signals 最小測試：抓 ERR／USER、濾掉 hook 擋下／輸出裡的 FAIL 字樣／系統注入、--ack 前移標記、沒新內容 rc=5
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export FI_STATE_DIR="$T/state"
J="$T/sess.jsonl"
pass=0; fail=0
ok() { if eval "$2"; then echo "PASS $1"; pass=$((pass+1)); else echo "FAIL $1"; fail=$((fail+1)); fi; }

cat > "$J" <<'EOF'
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"sed -n '/a/,+6p' f"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","is_error":true,"content":"Exit code 1\nsed: 1: unterminated regular expression"}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t2","name":"Bash","input":{"command":"git log x | head"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t2","content":"fatal: ambiguous argument 'x'"}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t3","name":"Bash","input":{"command":"bash test.sh"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t3","content":"FAIL c3 not found\nPASS c4"}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t4","name":"Bash","input":{"command":"rm -rf x"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t4","is_error":true,"content":"PreToolUse:Bash hook error: blocked"}]}}
{"type":"user","message":{"content":"不是這樣，應該是用 printf"}}
{"type":"user","message":{"content":"<command-name>/fi</command-name> 不是"}}
{"type":"user","isCompactSummary":true,"message":{"content":"This session is being continued 不是"}}
{"type":"user","message":{"content":"好，繼續"}}
EOF

out="$(python3 "$HERE/fi-signals.py" "$J")"; rc=$?
ok c1-rc0 '[ "$rc" = 0 ]'
ok c2-is_error 'printf "%s\n" "$out" | grep -q "ERR sed .* ⇒ sed: 1: unterminated"'
ok c3-strong 'printf "%s\n" "$out" | grep -q "ERR git log x .* ⇒ fatal: ambiguous"'
ok c4-no-fail-text '! printf "%s\n" "$out" | grep -q "bash test.sh"'
ok c5-no-hook '! printf "%s\n" "$out" | grep -q "rm -rf"'
ok c6-user 'printf "%s\n" "$out" | grep -q "USER 不是這樣"'
ok c7-user-count '[ "$(printf "%s\n" "$out" | grep -c " USER ")" = 1 ]'
python3 "$HERE/fi-signals.py" --ack "$J"
ok c8-ack '[ "$(cat "$FI_STATE_DIR/sess")" = 12 ]'
python3 "$HERE/fi-signals.py" "$J" >/dev/null; rc=$?
ok c9-nothing-new '[ "$rc" = 5 ]'
echo '{"type":"user","message":{"content":"又忘了 rc"}}' >> "$J"
out="$(python3 "$HERE/fi-signals.py" "$J")"
ok c10-only-new '[ "$(printf "%s\n" "$out" | wc -l | tr -d " ")" = 1 ] && printf "%s\n" "$out" | grep -q "L13 USER 又忘"'
python3 "$HERE/fi-signals.py" >/dev/null 2>&1; rc=$?
ok c11-usage '[ "$rc" = 2 ]'
echo "pass=$pass fail=$fail"
[ "$fail" = 0 ]
