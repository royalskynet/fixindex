#!/bin/bash
# devin-cc-hookwrap — Devin hook stdin → Claude Code 形狀，讓 cc 版 hook 腳本原樣可用。
# 用法：devin-cc-hookwrap.sh <指令...>     （stdin 轉寫後 pipe 給該指令）
# Devin 工具名 → cc 名：exec→Bash、edit→Edit、write→Write、notebook_edit→NotebookEdit、
# run_subagent→Task（prompt 欄位補 task）、read→Read。stdin 沒有 tool_name 的事件原樣透傳。
set -u
in="$(cat)"
printf '%s' "$in" | /opt/homebrew/bin/jq -c '
  .tool_name as $t
  | if $t == null then . else
      (.tool_name = ({exec:"Bash",edit:"Edit",write:"Write",notebook_edit:"NotebookEdit",run_subagent:"Task",read:"Read",find_file_by_name:"Glob",grep:"Grep",browser_preview:"WebFetch",webfetch:"WebFetch",web_search:"WebSearch"}[$t] // $t))
      | (if $t == "run_subagent" then .tool_input.prompt = (.tool_input.task // .tool_input.prompt) else . end)
    end
' | "$@"
