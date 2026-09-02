#!/bin/sh
# audit-history.sh — 唯讀憑證稽核：全歷史 + HEAD 現存，一網打盡
# 對固定兩個 repo 各跑兩種 gitleaks 掃描，缺一不可：
#   gitleaks detect --log-opts="--all"  → 歷史（含已刪除的檔案）
#   gitleaks detect --no-git            → HEAD 現存檔案
# 兩者結果不同。實測：project_effie_agent.md 只有 --no-git 抓得到，
# 全歷史掃描沒報（該檔的 leak 在掃描窗口外的舊 commit 或未變更過）。
#
# 安全要求：
#   一律 --redact=100，輸出只印 RuleID / File / Commit / Date，絕不印值。
#   唯讀：絕不修改任何檔案（mktemp 只在 /tmp）。
#   退出碼：任一掃描有 leak 回 1；無 leak 回 0。
#
# 重要：不得掛進任何 git hook。它掃全歷史，掛上去就是重演 R2 剛修掉
# 的「每次 push 掃全歷史」病。它是手動 / 排程稽核工具。

# 路徑一律走環境變數，不硬編。硬編會把「本機有哪些 repo、掛在哪」寫進
# 這個 public repo；那不是憑證，但也沒有必要公開，而 public repo 推出去
# 之後實務上收不回來（清歷史要 force push + 斷既有 clone，且 GitHub 快取
# 短期仍取得到舊物件）。
REPO_ROOT="${FIXINDEX_HOME:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
CONFIG="${FIXINDEX_GITLEAKS_CONFIG:-$REPO_ROOT/tools/gitleaks.toml}"
REDACT=100
OVERALL=0

# --- 印 JSON report：只取 RuleID/File/Commit/Date，絕不印 Secret/Match ---
print_report() {  # $1 = report json 路徑
    /usr/bin/python3 -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
except Exception as e:
    print("  (report unreadable: %s)" % e)
    sys.exit(0)
leaks = d if isinstance(d, list) else d.get("Leaks", d.get("findings", []))
if not leaks:
    print("  clean")
for x in leaks:
    commit = str(x.get("Commit", "") or "-")
    if len(commit) > 8: commit = commit[:8]
    date = str(x.get("Date", "") or "-")
    if len(date) > 10: date = date[:10]
    print("  %-28s %s  commit=%s date=%s" % (x.get("RuleID", "?"), x.get("File", "?"), commit, date))
' "$1"
}

scan_repo() {  # $1 = repo 絕對路徑  $2 = label
    repo="$1"; label="$2"
    if [ ! -d "$repo/.git" ] && [ ! -f "$repo/.git" ]; then
        echo "FATAL: not a git repo: $repo" >&2
        OVERALL=1
        return
    fi
    if ! command -v gitleaks >/dev/null 2>&1; then
        echo "FATAL: gitleaks not found on PATH" >&2
        OVERALL=1
        return
    fi
    echo ""
    echo "===== $label ($repo) ====="

    # 1) 歷史掃描（含已刪除檔案）
    hist=$(mktemp)
    gitleaks detect --source "$repo" --config "$CONFIG" --log-opts="--all" \
        --redact="$REDACT" --report-format json --report-path "$hist" \
        --no-banner >/dev/null 2>&1
    hist_rc=$?
    echo "--- 歷史 (log-opts=--all) ---"
    print_report "$hist"
    [ "$hist_rc" -ne 0 ] && OVERALL=1

    # 2) HEAD 現存掃描（工作樹檔案，不看 git 歷史）
    headr=$(mktemp)
    gitleaks detect --source "$repo" --config "$CONFIG" --no-git \
        --redact="$REDACT" --report-format json --report-path "$headr" \
        --no-banner >/dev/null 2>&1
    head_rc=$?
    echo "--- 現存 (--no-git) ---"
    print_report "$headr"
    [ "$head_rc" -ne 0 ] && OVERALL=1

    rm -f "$hist" "$headr"
}

# 引擎 repo：預設就是本腳本所在的 repo。
scan_repo "$REPO_ROOT" "engine repo"

# runbook 資料庫：位置因人而異，且多半是私有 repo —— 不給預設值。
# FIXINDEX_DIR 指向 fixes/，稽核對象是它的上一層（git repo 根）。
LOG_REPO="${FIXINDEX_LOG_REPO:-}"
if [ -z "$LOG_REPO" ] && [ -n "$FIXINDEX_DIR" ]; then
    LOG_REPO=$(CDPATH= cd -- "$FIXINDEX_DIR/.." 2>/dev/null && pwd)
fi
if [ -n "$LOG_REPO" ] && [ -d "$LOG_REPO/.git" ]; then
    scan_repo "$LOG_REPO" "runbook log repo"
else
    echo ""
    echo "跳過 runbook log repo：未設 FIXINDEX_LOG_REPO，且 FIXINDEX_DIR 未指向 git repo"
fi

echo ""
if [ "$OVERALL" -eq 0 ]; then
    echo "AUDIT CLEAN"
else
    echo "AUDIT: findings above (exit 1)"
fi
exit "$OVERALL"