#!/usr/bin/env bash
# fi-reminder.sh — Claude Code Stop hook（三點式 fixindex loop 第 3 點：完工收尾 fi）。
# 若本次（transcript）有除錯/修復跡象、但沒呼叫 fixindex fi/new/auto 記入 runbook，
# 回 {"decision":"block"} 強制模型補記（或說明為何不需記）後才能停。
# stop_hook_active=true 表示已經 block 過一輪 → 靜默放行，防無限迴圈。
# 由 Claude Code 掛在 settings.json "hooks"."Stop"。

set -u
INPUT="$(cat)"

read -r TP ACTIVE < <(printf '%s' "$INPUT" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print(d.get("transcript_path") or "-", str(bool(d.get("stop_hook_active"))).lower())
' 2>/dev/null) || exit 0

# 已 block 過一輪 → 放行（模型該做的已做或已表態）
[[ "${ACTIVE:-false}" == "true" ]] && exit 0
[[ -n "${TP:-}" && "$TP" != "-" && -f "$TP" ]] || exit 0

# 已記？有 fixindex 寫入呼叫 → 靜默
if grep -qE 'fixindex (fi|new|auto)' "$TP" 2>/dev/null; then
  exit 0
fi

# 規模門檻：小任務（工具呼叫少）不值 fi 成本 → 靜默。
# 以 transcript 內 tool_use 行數近似總呼叫數；閾值 10。
# grep -c 無命中時自己就印 0（exit 1），不能再 || echo 0 疊第二行。
CALLS=$(grep -cE '"type": ?"tool_use"' "$TP" 2>/dev/null)
[[ "${CALLS:-0}" =~ ^[0-9]+$ ]] || CALLS=0
[[ "$CALLS" -lt 10 ]] && exit 0

# 本次有除錯/修復跡象？
if grep -qiE 'error|錯誤|bug|fix(ed)?|修好|修復|除錯|debug|root cause|根因|崩|crashed?|timeout|401|fail(ed)?|stack trace|重試' "$TP" 2>/dev/null; then
  printf '%s' '{"decision":"block","reason":"fi-reminder: 本次疑似修過 defect，但未見 fixindex fi/new/auto 記入。現在補記（printf \"SYMPTOM: ...\\nFIX: ...\" | fixindex fi，含實測數據與無效嘗試）；若確實無 defect 可記，一句話說明後即可停。"}'
  exit 0
fi
exit 0
