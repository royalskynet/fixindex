#!/bin/bash
# fi-reminder-devin.sh — Devin Stop hook（advisory，不 block）。
# 兩件事：
#   1. 本 session 上次 /fi 之後還有未處理的除錯／糾正訊號（fi-signals-devin rc=0）→ 提醒跑 /fi。
#   2. fixindex 有未同步積壓（status --assert-clean ≠0）→ 提醒補推。
# 對應 cc 版 ~/.claude/hooks/fi-reminder.sh（那版吃 Claude Code jsonl＋可 block，這版只提示）。
set -u
INPUT="$(cat)"
SID="$(printf '%s' "$INPUT" | /opt/homebrew/bin/jq -r '.session_id // empty' 2>/dev/null)"
T=""
if [ -n "$SID" ]; then
  T="$(grep -l "\"$SID\"" "$HOME"/.local/share/devin/cli/transcripts/*.json 2>/dev/null | head -1)"
fi
[ -z "$T" ] && T="$(ls -t "$HOME"/.local/share/devin/cli/transcripts/*.json 2>/dev/null | head -1)"
[ -z "$T" ] && exit 0

MSG=""
if python3 "$HOME/dev/fixindex/tools/fi-signals-devin.py" "$T" >/dev/null 2>&1; then
  MSG="本 session 有未處理的除錯／使用者糾正訊號：建議跑 fi 流程回顧，值得記的寫進 fixindex"
fi
if ! fixindex status --assert-clean >/dev/null 2>&1; then
  MSG="${MSG:+$MSG；}fixindex 有未同步積壓（離線或 push 失敗），收尾前補推"
fi
[ -z "$MSG" ] && exit 0
/opt/homebrew/bin/jq -nc --arg m "$MSG" '{systemMessage:$m, hookSpecificOutput:{hookEventName:"Stop", additionalContext:$m}}'
