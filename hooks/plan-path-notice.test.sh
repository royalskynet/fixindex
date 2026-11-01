#!/usr/bin/env bash
# plan-path-notice.test.sh — hooks/plan-path-notice.js 的行為測試（2026-11-02 加）。
#
# 為什麼要有：這支 hook 的線上版本被一份 36K 舊副本蓋掉過（~/.claude/hooks 下不是
# symlink，兩份各自長），線上實際跑的根本不是 repo 這份，而且沒有任何測試會發現。
# 另加三支 guard 會 exec 它，它壞掉＝所有 PreToolUse 靜默全放行。
#
# 在 mktemp 目錄造假 HOME（guard-state 寫在那裡），用 stdin 丟 payload，斷言：
#   1. Write 且本 session 沒查舊帳 → 注入 fixindex 提醒，且只提醒一次
#   2. 同 session 已跑過 fixindex find → 靜默放行
#   3. ExitPlanMode 帶 planFilePath → 注入「計畫檔：<路徑>」，並把路徑釘給同 session
#   4. 空 payload／壞 JSON → 仍然 rc 0 且輸出合法 JSON（fail-open）
# 全過最後印 PASS，否則印 FAIL 細節並 exit 1。不打網路、不碰真的 ~/.claude。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/plan-path-notice.js"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ppn.XXXXXX")" || { echo "FAIL mktemp" >&2; exit 1; }
trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/home"; mkdir -p "$HOME"

fail=0
chk() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: got '$2' want '$3'"; fail=1; fi; }
# run_hook <stdin 內容>：印 hook 的 stdout
run_hook() { printf '%s' "$1" | node "$HOOK"; }

tp="$WORK/t.jsonl"; : > "$tp"

write_payload() { printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$1" "$2" "$WORK" "$WORK/a.md"; }

# 1. 沒查舊帳 → 提醒，一次
o="$(run_hook "$(write_payload s1 "$tp")")"
case "$o" in *"fixindex find"*) chk "未查舊帳 → 提醒" 1 1 ;; *) chk "未查舊帳 → 提醒 (輸出: $o)" 1 0 ;; esac
o2="$(run_hook "$(write_payload s1 "$tp")")"
case "$o2" in *"fixindex find"*) chk "同 session 第二次不重複提醒" 0 1 ;; *) chk "同 session 第二次不重複提醒" 0 0 ;; esac

# 2. 已跑 fixindex find → 靜默（ran flag 由職能 2 在 Bash 前寫入，實測；transcript 不是判定來源）
run_hook "{\"session_id\":\"s2\",\"cwd\":\"$WORK\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"fixindex find x\"}}" >/dev/null
o="$(run_hook "$(write_payload s2 "$tp")")"
case "$o" in *"fixindex find"*) chk "查過舊帳 → 靜默" 0 1 ;; *) chk "查過舊帳 → 靜默" 0 0 ;; esac

# 3. ExitPlanMode → 注入計畫檔路徑 + 釘給同 session
plan="$WORK/plan.md"; echo '# plan' > "$plan"
o="$(run_hook "{\"session_id\":\"s3\",\"transcript_path\":\"$tp\",\"cwd\":\"$WORK\",\"tool_name\":\"ExitPlanMode\",\"tool_input\":{\"planFilePath\":\"$plan\"}}")"
case "$o" in *"計畫檔：$plan"*) chk "ExitPlanMode → 注入計畫檔" 1 1 ;; *) chk "ExitPlanMode → 注入計畫檔 (輸出: $o)" 1 0 ;; esac
# 延續提醒只在 Bash 分支發（設計如此）；Edit/Write 不會帶回 plan
bp() { printf '{"session_id":"s3","transcript_path":"%s","cwd":"%s","tool_name":"Bash","tool_input":{"command":"echo hi"}}' "$tp" "$WORK"; }
o="$(run_hook "$(bp)")"
case "$o" in *"$plan"*) chk "同 session 下一道指令帶回釘住的計畫檔" 1 1 ;; *) chk "同 session 下一道指令帶回釘住的計畫檔 (輸出: $o)" 1 0 ;; esac

# 4. fail-open
o="$(run_hook '')"; rc=$?
chk "空 payload rc" "$rc" 0
case "$o" in *'"continue":true'*) chk "空 payload 輸出合法 JSON" 1 1 ;; *) chk "空 payload 輸出合法 JSON (輸出: $o)" 1 0 ;; esac
o="$(run_hook '{bad json')"; rc=$?
chk "壞 JSON rc" "$rc" 0

[ "$fail" = 0 ] && echo "PASS plan-path-notice" || echo "FAIL plan-path-notice"
exit "$fail"
