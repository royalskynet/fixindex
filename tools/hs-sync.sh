#!/usr/bin/env bash
# hs-sync.sh — 把 fixindex 條目單向同步到本機 Hindsight。
#
# 用法：
#   hs-sync.sh [--dry-run] <fixes/0001-green.md> [檔案…]
#   hs-sync.sh [--dry-run] --all <fixes目錄>
#
# 規則：status 為 superseded／stale → 刪掉 bank 裡的 fix-<id>；
#       其他 → 整檔文字餵進 bank（document_id=fix-<id>）。
#       檔名非「數字-」開頭的（.template.md、README.md）跳過。
#
# 這支會被 git hook 在背景呼叫，所以失敗絕對不能擋 commit：
# 連不上或非 2xx 都只寫一行到 HS_LOG 然後繼續下一檔，整支結束一律 exit 0。
# 唯一不碰 API 的路徑是 --dry-run：每檔印一行 RETAIN <id> 或 DELETE <id>。
#
# 環境變數：HS_API（預設 http://127.0.0.1:8888）、HS_BANK（預設 fixindex）、
#           HS_LOG（預設 $HOME/.hindsight/logs/hs-sync.log）。
set -u

HS_API="${HS_API:-http://127.0.0.1:8888}"
HS_BANK="${HS_BANK:-fixindex}"
HS_LOG="${HS_LOG:-$HOME/.hindsight/logs/hs-sync.log}"
export HS_API HS_BANK HS_LOG

usage() {
    cat >&2 <<'EOF'
usage: hs-sync.sh [--dry-run] <fix.md> [更多檔案…]
       hs-sync.sh [--dry-run] --all <fixes目錄>
EOF
}

DRY_RUN=0
MODE=list
ALL_DIR=''
FILES=()

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            ;;
        --all)
            MODE=all
            shift
            ALL_DIR="${1:-}"
            if [ -z "$ALL_DIR" ]; then
                echo "hs-sync: --all 後面要給 fixes 目錄" >&2
                exit 0
            fi
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            while [ $# -gt 0 ]; do
                FILES+=("$1")
                shift
            done
            break
            ;;
        -*)
            echo "hs-sync: 不認得的選項：$1" >&2
            usage
            exit 0
            ;;
        *)
            FILES+=("$1")
            ;;
    esac
    shift
done

if [ "$MODE" = all ]; then
    if [ ! -d "$ALL_DIR" ]; then
        echo "hs-sync: 沒有這個目錄：$ALL_DIR" >&2
        exit 0
    fi
    while IFS= read -r found; do
        [ -n "$found" ] && FILES+=("$found")
    done < <(find "$ALL_DIR" -maxdepth 1 -type f -name '*.md' | LC_ALL=C sort)
else
    if [ ${#FILES[@]} -eq 0 ]; then
        usage
        exit 0
    fi
fi

# 每檔一個獨立行程：單檔炸掉（python 缺、檔案怪）不拖死整輪。
# ${FILES[@]+…} 是 bash 3.2 在 set -u 下的空陣列保險。
first=1
for f in ${FILES[@]+"${FILES[@]}"}; do
    base="${f##*/}"
    # 只收「數字-」開頭的條目檔；.template.md／README.md 一律跳過。
    case "$base" in
        [0-9]*-*) ;;
        *) continue ;;
    esac
    [ -f "$f" ] || continue

    if [ "$MODE" = all ]; then
        [ "$first" -eq 1 ] || sleep 0.2
        first=0
    fi

    /usr/bin/python3 - "$f" "$DRY_RUN" <<'PY' || true
import json
import os
import re
import sys
import urllib.error
import urllib.request

path = sys.argv[1]
dry = sys.argv[2] == "1"

api = os.environ.get("HS_API", "http://127.0.0.1:8888").rstrip("/")
bank = os.environ.get("HS_BANK", "fixindex")
log = os.environ.get("HS_LOG", os.path.expanduser("~/.hindsight/logs/hs-sync.log"))

DELETE_STATUS = ("superseded", "stale")


def logerr(msg):
    # 日誌寫不動就算了，不許因為記錄失敗而中斷同步。
    try:
        parent = os.path.dirname(log)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(log, "a") as fh:
            fh.write(msg + "\n")
    except OSError:
        pass


def unquote(val):
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        return val[1:-1]
    return val


def frontmatter(text):
    """回 (id, status)。frontmatter 沒有 id 就退回檔名的數字前綴。"""
    lines = text.splitlines()
    fid = status = None
    if not lines or lines[0].strip() != "---":
        return os.path.basename(path).split("-", 1)[0], ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), unquote(m.group(2))
        if key == "id" and fid is None:
            fid = val
        elif key == "status" and status is None:
            status = val
    if not fid:
        fid = os.path.basename(path).split("-", 1)[0]
    return fid, status or ""


def call(method, url, payload=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


try:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
except OSError as exc:
    logerr("hs-sync: 讀不到 %s：%s" % (path, exc))
    sys.exit(0)

fid, status = frontmatter(text)
doc = "fix-%s" % fid
action = "DELETE" if status.strip().lower() in DELETE_STATUS else "RETAIN"

if dry:
    print("%s %s" % (action, fid))
    sys.exit(0)

try:
    if action == "RETAIN":
        body = {
            "items": [{
                "content": text,
                "document_id": doc,
                "context": "fixindex %s" % fid,
            }],
            "async": True,
        }
        call("POST", "%s/v1/default/banks/%s/memories" % (api, bank), body)
    else:
        try:
            call("DELETE", "%s/v1/default/banks/%s/documents/fix-%s" % (api, bank, fid))
        except urllib.error.HTTPError as exc:
            # 404＝本來就沒這筆，語意上等於刪成功。
            if exc.code != 404:
                raise
except urllib.error.HTTPError as exc:
    logerr("hs-sync: %s %s HTTP %s" % (action, doc, exc.code))
except Exception as exc:
    logerr("hs-sync: %s %s %s: %s" % (action, doc, type(exc).__name__, exc))

sys.exit(0)
PY
done

exit 0