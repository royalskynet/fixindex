#!/bin/sh
# secret-scan.sh — gitleaks 薄 wrapper, fail-closed
# 用法: secret-scan.sh staged | push
# staged = pre-commit 模式 (掃暫存區 diff); push = pre-push 模式 (掃新增 commit range)
#
# 安全模型: FAIL-CLOSED — gitleaks 消失 = 擋下 commit/push, 不放行。
# 引擎: gitleaks (不自刻 regex), config 指向同目錄 gitleaks.toml。
# --redact=100 是硬性要求: guard.js 攔憑證外送, 掃描器印命中字串 = 自己洩漏。

CONFIG="/Users/51mini/dev/fixindex/tools/gitleaks.toml"
TARGET="."

# --- 逃生門 (第一個判斷) ---
if [ "$SECRET_SCAN_OFF" = "1" ]; then
    echo "WARNING: SECRET_SCAN_OFF=1 — secret scan disabled (escape hatch)" >&2
    exit 0
fi

# --- fail-closed 前置: gitleaks 必須找得到, 否則擋 (不可放行) ---
if ! command -v gitleaks >/dev/null 2>&1; then
    echo "FATAL: gitleaks not found on PATH — refusing commit/push (fail-closed)" >&2
    exit 1
fi

MODE="$1"
case "$MODE" in
  staged)
    # pre-commit: 掃暫存區 (--staged)
    # -v 讓 finding 明細 (RuleID/File/Line/fingerprint) 印出 (驗收 #7)。
    # 不加 2>/dev/null; --redact=100 保證不外洩完整憑證。
    gitleaks git --staged -v --no-banner --redact=100 --exit-code 1 \
        --config "$CONFIG" "$TARGET"
    exit $?
    ;;

  push)
    # pre-push: git 餵給 stdin 每行: <local ref> <local sha> <remote ref> <remote sha>
    overall=0
    while read -r line; do
        [ -z "$line" ] && continue
        lsha=$(echo "$line" | awk '{print $2}')
        rsha=$(echo "$line" | awk '{print $4}')
        # 跳過 local sha 全零 (刪分支)
        if [ "$lsha" = "0000000000000000000000000000000000000000" ]; then
            continue
        fi
        # range: 新分支(rsha 全零)→ 單點 lsha; 否則 rsha..lsha
        if [ "$rsha" = "0000000000000000000000000000000000000000" ]; then
            range="$lsha"
        else
            range="$rsha..$lsha"
        fi
        gitleaks git -v --no-banner --redact=100 --exit-code 1 \
            --config "$CONFIG" --log-opts="--all $range" "$TARGET"
        rc=$?
        if [ "$rc" != "0" ]; then
            overall=1
        fi
    done
    exit $overall
    ;;

  *)
    echo "FATAL: unknown mode '$MODE' — usage: staged | push" >&2
    exit 1
    ;;
esac