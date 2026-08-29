#!/usr/bin/env bash
# golden_run.sh — 對 golden corpus 跑 fixindex find，算 recall@5 / precision@5 / MRR。
# 語料路徑由環境變數 FIXINDEX_GOLDEN 指定（不得寫死）。未設就印 usage 並 exit 2。
# 對每個 case 跑 FIXINDEX_NO_SYNC=1 FIXINDEX_SEMANTIC=0 fixindex find "<query>"，
# 解析輸出的 hit 行取前 5 名，最後印一行：
#   cases=<N> recall@5=<0.xx> precision@5=<0.xx> mrr=<0.xx>
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

python3 - "$results" <<'PY'
import json, sys

recall_hits = 0
prec_sum = 0.0
mrr_sum = 0.0
cases = 0
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.rstrip("\n")
    if not line:
        continue
    cases += 1
    case_json, hits_csv = line.rsplit("\t", 1)
    c = json.loads(case_json)
    expect = set(c.get("expect_ids", []))
    top5 = [h for h in hits_csv.split(",") if h][:5]

    hit_count = sum(1 for h in top5 if h in expect)
    if hit_count > 0:
        recall_hits += 1
    prec_sum += hit_count / max(len(top5), 1)

    # MRR: 第一個命中的名次倒數
    for i, h in enumerate(top5):
        if h in expect:
            mrr_sum += 1.0 / (i + 1)
            break

recall = recall_hits / cases if cases else 0.0
prec = prec_sum / cases if cases else 0.0
mrr = mrr_sum / cases if cases else 0.0
print(f"cases={cases} recall@5={recall:.2f} precision@5={prec:.2f} mrr={mrr:.2f}")
PY

exit 0