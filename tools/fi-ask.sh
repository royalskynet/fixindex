#!/usr/bin/env bash
# fi-ask — /fi 的 LLM 單回合呼叫（fi_pipeline 的 FI_ASK_CMD 預設）。介面同 ds-run.sh --ask：<dir> --ask "<問題>"，答案寫 <dir>/task/notes.md。
# 不走工具多回合：<dir> 頂層的檔全部用 -f 附進訊息。140K 逐字稿用 flash 多回合讀要約 3 分鐘，附檔單回合的免費模型約 20 秒（11-15 實測）。
# 模型依序試 FI_MODELS（只放免費層），每個最多 FI_ASK_TIMEOUT 秒，且不超過 FI_DEADLINE_AT（epoch 秒）。
# 退出碼：0 有答案｜2 用法錯誤｜4 全部模型失敗或逾時
set -u
[ $# -ge 3 ] && [ "$2" = --ask ] || { echo "用法：fi-ask.sh <dir> --ask <問題>" >&2; exit 2; }
dir="$1"; q="$3"
cd "$dir" || exit 2
mkdir -p task
files=()
for f in *; do [ -f "$f" ] && files+=(-f "$f"); done

# ponytail: 模型清單寫死 11-15 實測最快的兩個免費模型；免費池換血時改 FI_MODELS 或預設值
for m in ${FI_MODELS:-kilo/baidu/ernie-5.5-flash-preview:free kilo/particle-ai/particle-1:free}; do
  limit="${FI_ASK_TIMEOUT:-60}"
  if [ -n "${FI_DEADLINE_AT:-}" ]; then
    left=$(( FI_DEADLINE_AT - $(date +%s) ))
    [ "$left" -lt "$limit" ] && limit="$left"
  fi
  [ "$limit" -ge 5 ] || { echo "fi-ask: 時限已到" >&2; exit 4; }
  # macOS 沒有 timeout：開新 process group，逾時整組 kill，免得 opencode 的子程序留著
  perl -e 'my $t = shift; my $p = fork; die unless defined $p;
    if (!$p) { setpgrp(0, 0); exec @ARGV or exit 127 }
    $SIG{ALRM} = sub { kill "KILL", -$p; waitpid($p, 0); exit 124 };
    alarm $t; waitpid($p, 0); exit(($? & 127) ? 128 + ($? & 127) : $? >> 8)' \
    "$limit" opencode run --agent plan -m "$m" "$q" ${files[@]+"${files[@]}"} > task/notes.md 2> task/exec.log </dev/null
  rc=$?
  if [ "$rc" = 0 ] && [ -s task/notes.md ]; then echo "fi-ask: PASS $m"; exit 0; fi
  echo "fi-ask: $m rc=$rc，換下一個" >&2
done
exit 4
