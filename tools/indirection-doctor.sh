#!/bin/bash
# indirection-doctor.sh — 間接層運作狀態逐條斷言
# 讀 INDIRECTION_MANIFEST（env 覆寫，預設同目錄 indirection-manifest.json）
# 輸出對齊表格: KIND  ID  PASS|FAIL|KNOWN  detail
# 絕不印任何檔案內容；detail 只寫路徑/remote 名/md5 短碼/錯誤原因。
# 結尾: indirection-doctor: N pass / M fail / K known
# exit: expect:pass 條目 FAIL → 1；否則 0
# --json: 輸出一個 JSON 陣列（供 watchdog 解析）

MANIFEST="${INDIRECTION_MANIFEST:-$(dirname "$0")/indirection-manifest.json}"
MODE="${1:-table}"

command -v jq >/dev/null 2>&1 || { echo "FATAL: jq not found" >&2; exit 2; }

[ -f "$MANIFEST" ] || { echo "FATAL: manifest not found: $MANIFEST" >&2; exit 2; }

# ---- 判定 helper: 給 kind + 檢查物件, echo PASS|FAIL|KNOWN ----
# 回傳: 0=PASS, 1=FAIL, 2=KNOWN(skip)
check_one() {
  local kind="$1"
  local id="$2"
  local expect="$3"
  local actual_ok=0   # 1=實際狀態OK(符合宣告)
  local note=""

  case "$kind" in
    symlink)
      local path=""
      path=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .path' "$MANIFEST")
      if [ -L "$path" ] || { [ -f "$path" ] && [ ! -L "$path" ]; }; then
        actual_ok=1; note="$path (存在)"
      else
        note="$path (缺)"
      fi
      ;;
    git_remote)
      local repo remote
      repo=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .repo' "$MANIFEST")
      remote=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .remote' "$MANIFEST")
      if timeout 20 git -C "$repo" ls-remote --exit-code "$remote" >/dev/null 2>&1; then
        actual_ok=1; note="$repo $remote (可達)"
      else
        note="$repo $remote (不可達/timeout)"
      fi
      ;;
    git_hook)
      local repo hook
      repo=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .repo' "$MANIFEST")
      hook=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .hook' "$MANIFEST")
      local hpath="$repo/.git/hooks/$hook"
      if [ -f "$hpath" ] && [ -x "$hpath" ]; then
        local target=""
        # 是 delegator（含 S=" 那行）→ 被指到腳本也要存在可執行
        if grep -q '^S="' "$hpath" 2>/dev/null; then
          target=$(grep '^S="' "$hpath" | head -1 | sed 's/^S="//; s/"$//')
          if [ -n "$target" ] && [ -f "$target" ] && [ -x "$target" ]; then
            actual_ok=1; note="$hpath -> $target"
          else
            note="$hpath delegator 指向的 $target 缺/不可執行"
          fi
        else
          actual_ok=1; note="$hpath (可執行)"
        fi
      else
        note="$hpath 缺/不可執行"
      fi
      ;;
    hooks_path_unset)
      local repo
      repo=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .repo' "$MANIFEST")
      local out=""
      if [ "$repo" = "global" ]; then
        out=$(git config --global --get core.hooksPath 2>/dev/null)
      else
        out=$(git -C "$repo" config --get core.hooksPath 2>/dev/null)
      fi
      if [ -z "$out" ]; then
        actual_ok=1; note="core.hooksPath 未設定"
      else
        note="core.hooksPath=$out"
      fi
      ;;
    md5_fanout)
      local paths=""
      paths=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .paths[]' "$MANIFEST")
      local all_exist=1
      local missing=""
      local hashes=""
      local first=""
      local same=1
      local cnt=0
      local p h
      # 逐行讀（避免 mapfile, macOS bash 3.2 無此內建）
      while IFS= read -r p; do
        [ -z "$p" ] && continue
        cnt=$((cnt+1))
        if [ ! -f "$p" ]; then
          all_exist=0
          missing="$missing $p"
          continue
        fi
        h=$(md5 -q "$p" 2>/dev/null)
        if [ -z "$first" ]; then
          first="$h"
        elif [ "$h" != "$first" ]; then
          same=0
        fi
        hashes="$hashes ${h:0:6}"
      done <<< "$paths"
      if [ "$all_exist" = "0" ]; then
        note="缺檔:$missing"
      elif [ "$same" = "1" ]; then
        actual_ok=1; note="${cnt}面一致: ${first:0:10}…"
      else
        note="md5 不一致:$hashes"
      fi
      ;;
    exec_exists)
      local cmd
      cmd=$(jq -r --arg id "$id" '.checks[] | select(.id==$id) | .cmd' "$MANIFEST")
      if command -v "$cmd" >/dev/null 2>&1; then
        actual_ok=1; note="$cmd (存在)"
      else
        note="$cmd (缺)"
      fi
      ;;
    *)
      note="未知 kind: $kind";;
  esac

  # 判定 PASS/FAIL (expect 相符性)
  local status
  if [ "$actual_ok" = "1" ]; then
    if [ "$expect" = "pass" ]; then status="PASS"; else status="FAIL"; fi
  else
    if [ "$expect" = "fail" ]; then status="PASS"; else status="FAIL"; fi
  fi

  echo "$status $note"
}

# 逐條跑
PASS_CT=0; FAIL_CT=0; KNOWN_CT=0
declare -a json_out=()

while IFS=$'\t' read -r kind id expect; do
  res=$(check_one "$kind" "$id" "$expect")
  status="${res%% *}"
  detail="${res#* }"

  if [ "$MODE" = "--json" ]; then
    json_out+=("$(jq -nc --arg k "$kind" --arg id "$id" --arg s "$status" --arg d "$detail" '{kind:$k,id:$id,status:$s,detail:$d}')")
  else
    printf '%-14s  %-24s  %-4s  %s\n' "$kind" "$id" "$status" "$detail"
  fi

  case "$status" in
    PASS) PASS_CT=$((PASS_CT+1));;
    FAIL) FAIL_CT=$((FAIL_CT+1));;
    *)    KNOWN_CT=$((KNOWN_CT+1));;
  esac
done < <(jq -r '.checks[] | [.kind,.id,.expect] | @tsv' "$MANIFEST")

if [ "$MODE" = "--json" ]; then
  printf '[\n%s\n]\n' "$(IFS=,; echo "${json_out[*]}")"
else
  echo ""
  echo "indirection-doctor: $PASS_CT pass / $FAIL_CT fail / $KNOWN_CT known"
fi

# exit code: expect:pass 且 FAIL → 1
[ "$FAIL_CT" -gt 0 ] && exit 1 || exit 0