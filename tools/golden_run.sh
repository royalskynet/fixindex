#!/usr/bin/env bash
# golden_run.sh — 對 golden corpus 跑 fixindex find，分桶算指標。
# 語料路徑由環境變數 FIXINDEX_GOLDEN 指定（不得寫死）。未設就印 usage 並 exit 2。
# 對每個 case 跑 FIXINDEX_NO_SYNC=1 FIXINDEX_SEMANTIC=0 fixindex find \"<query>\"，
# 解析輸出的 hit 行取前 5 名。分桶輸出：
#   bucket=verbatim    n=NNN  recall@5=0.xx  mrr=0.xx  median_rank=N
#   bucket=paraphrase  n=NNN  recall@5=0.xx  mrr=0.xx  median_rank=N
#   bucket=negative    n=NNN  false_hit_rate=0.xx
# 結果同時分桶寫入 baseline.json，預設落在**語料旁邊**（跟著資料走，不落進 CLI repo）；
# 可用 FIXINDEX_GOLDEN_BASELINE 覆寫。
# exit 0（有跑完就 0；分數高低不影響 exit code）。
set -u

G="${FIXINDEX_GOLDEN:-}"
if [ -z "$G" ]; then
  echo "usage: FIXINDEX_GOLDEN=<cases.jsonl> bash $0" >&2
  exit 2
fi
if [ ! -f "$G" ]; then
  echo "golden corpus not found: $G" >&2
  exit 2
fi

BASELINE="${FIXINDEX_GOLDEN_BASELINE:-$(dirname "$G")/baseline.json}"

results="$(mktemp)"
# mktemp 在受限環境會失敗並回空字串，而 `>> ""` 只會逐行報錯、整輪靜默產不出資料。
[ -n "$results" ] || { echo "golden_run: mktemp 失敗（受限環境？）" >&2; exit 1; }
trap 'rm -f "$results"' EXIT
: > "$results"

while IFS= read -r line || [ -n "$line" ]; do
  [ -n "$line" ] || continue
  query="$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["query"])')"
  out="$(FIXINDEX_NO_SYNC=1 FIXINDEX_SEMANTIC=0 fixindex find "$query" 2>/dev/null)"
  hits=()
  while IFS= read -r hl; do
    key="$(printf '%s' "$hl" | sed -nE 's/^[[:space:]]*([0-9]{4}#[0-9]+).*/\1/p')"
    if [ -n "$key" ]; then
      hits+=("$key")
    fi
  done <<< "$out"
  hits=("${hits[@]:0:5}")
  printf '%s\t%s\n' "$line" "$(IFS=,; echo "${hits[*]}")" >> "$results"
done < "$G"

python3 - "$results" "$BASELINE" <<'PY'
import json, statistics, sys

results_path, baseline_path = sys.argv[1], sys.argv[2]

buckets = {"verbatim": {"n": 0, "recall_hits": 0, "mrr_sum": 0.0, "ranks": [], "hits": 0, "top5_total": 0},
           "paraphrase": {"n": 0, "recall_hits": 0, "mrr_sum": 0.0, "ranks": [], "hits": 0, "top5_total": 0},
           "negative": {"n": 0, "false_hits": 0}}

for line in open(results_path, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line:
        continue
    case_json, hits_csv = line.rsplit("\t", 1)
    c = json.loads(case_json)
    bucket = c.get("bucket", "verbatim")
    if bucket not in buckets:
        continue
    b = buckets[bucket]
    b["n"] += 1
    top5 = [h for h in hits_csv.split(",") if h][:5]

    if bucket == "negative":
        expect_not = set(c.get("expect_not", []))
        if any(h in expect_not for h in top5):
            b["false_hits"] += 1
        continue

    expect = set(c.get("expect_ids", []))
    if any(h in expect for h in top5):
        b["recall_hits"] += 1
    # MRR: 第一個命中的名次倒數；未命中 MRR=0
    for i, h in enumerate(top5):
        if h in expect:
            b["mrr_sum"] += 1.0 / (i + 1)
            b["ranks"].append(i + 1)
            break
    else:
        b["ranks"].append(6)  # 未命中以 rank=6（在 top-5 之外）計

def fmt_bucket(name, b):
    if not b["n"]:
        return f"bucket={name:<11} n=0"
    if name == "negative":
        fhr = b["false_hits"] / b["n"]
        return f"bucket={name:<11} n={b['n']:<4} false_hit_rate={fhr:.2f}"
    recall = b["recall_hits"] / b["n"]
    mrr = b["mrr_sum"] / b["n"]
    median_rank = statistics.median(b["ranks"])
    return f"bucket={name:<11} n={b['n']:<4} recall@5={recall:.2f}  mrr={mrr:.2f}  median_rank={median_rank}"

out_lines = [fmt_bucket("verbatim", buckets["verbatim"]),
             fmt_bucket("paraphrase", buckets["paraphrase"]),
             fmt_bucket("negative", buckets["negative"])]
for ln in out_lines:
    print(ln)

blob = {"generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "buckets": {}}
for name, b in buckets.items():
    if b["n"] == 0:
        blob["buckets"][name] = {"n": 0}
        continue
    if name == "negative":
        blob["buckets"][name] = {"n": b["n"], "false_hit_rate": round(b["false_hits"] / b["n"], 4)}
    else:
        blob["buckets"][name] = {
            "n": b["n"],
            "recall@5": round(b["recall_hits"] / b["n"], 4),
            "mrr": round(b["mrr_sum"] / b["n"], 4),
            "median_rank": statistics.median(b["ranks"]),
        }
with open(baseline_path, "w", encoding="utf-8") as f:
    json.dump(blob, f, ensure_ascii=False, indent=2)
PY

exit 0