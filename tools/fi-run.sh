#!/usr/bin/env bash
# fi-run — /fi 一條龍：fi-deep.sh 產工作目錄 → fi_pipeline.py（LLM 兩段走 fi-ask 免費模型單回合，各塊平行）→ 工單驗收段 → 印精簡報告。
# 主 session 只跑這一條，不派 deep、不讀 part 檔。用法：fi-run [session.jsonl]
# 退出碼：0 完成且驗收過｜5 上次 /fi 後沒有新內容｜其他＝失敗階段的 rc（fi-deep 2/3/4、pipeline 3/4/6、驗收 1）
# 時限：FI_BUDGET 秒（預設 90）從進來就起算，pipeline 與 fi-ask 照 FI_DEADLINE_AT 收手；超時 rc=6，不寫入、不前移標記
set -u
T0=$(date +%s)
export FI_DEADLINE_AT=$(( T0 + ${FI_BUDGET:-90} ))
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$(FI_MODE=pipeline bash "$HERE/fi-deep.sh" "$@" 2>&1)"; rc=$?
if [ "$rc" = 5 ]; then printf '%s\n' "$OUT" | tail -1; exit 5; fi
if [ "$rc" != 0 ]; then printf '%s\n' "$OUT" | tail -5; echo "fi-run: fi-deep rc=$rc"; exit "$rc"; fi
TASK="$(printf '%s\n' "$OUT" | tail -1 | cut -d' ' -f2)"
R="$(printf '%s\n' "$OUT" | sed -n 's/^report: //p' | tail -1)"
W="$(dirname "$R")"

python3 "$HERE/fi_pipeline.py" "$W" >"$W/pipeline.log" 2>&1; rc=$?
if [ "$rc" != 0 ]; then tail -20 "$W/pipeline.log"; echo "fi-run: pipeline rc=${rc}，$(( $(date +%s) - T0 ))s（W=${W}）"; exit "$rc"; fi

awk '/^```bash$/{f=1;next} /^```$/{f=0} f' "$TASK" > "$W/accept.sh"
bash "$W/accept.sh" >"$W/accept.log" 2>&1; rc=$?
# 報告只印條目行，不印 status JSON
awk '/^## status$/{exit} {print}' "$R"
if [ "$rc" != 0 ]; then tail -10 "$W/accept.log"; echo "fi-run: 驗收 rc=${rc}（W=${W}）"; exit 1; fi
el=$(( $(date +%s) - T0 ))
if [ "$el" -gt "${FI_BUDGET:-90}" ]; then echo "fi-run: 驗收過但超過時限（${el}s > ${FI_BUDGET:-90}s，W=${W}）"; exit 6; fi
echo "fi-run: OK（驗收過，${el}s，W=${W}）"
