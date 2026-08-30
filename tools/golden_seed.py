#!/usr/bin/env python3
"""golden_seed.py — 從真實語料自動產生 golden corpus 測試 case。

讀取目錄由環境變數 FIXINDEX_DIR 指定（不得寫死路徑）。
種子來源：fixes/*.md 裡 body 含 `**Rule:**` 的條目。對每一筆取 frontmatter
`symptoms` 的第一條當 query、該條目自身的 `<4位id>#<section序號>` 當
expect_ids（section 序號沿用 fxsearch/fxblurb 的 enumerate 語意：
`f'{fid}#{sn+1}'`）。

跳過：symptoms 缺失或為空的、status: superseded 的。

輸出 JSONL 到 argv[1]，一行一 case。印出 seeded=<N> skipped=<M>。
"""
import glob
import importlib.util
import json
import os
import re
import sys

RULE_RE = re.compile(r"\*\*Rule:\*\*")


def load_fxmeta():
    """載入 repo 權威解析模組（只讀使用，不改它）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    fxmeta_path = os.path.join(here, "..", "fxmeta.py")
    spec = importlib.util.spec_from_file_location("fxmeta", fxmeta_path)
    fxmeta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fxmeta)
    return fxmeta


def main():
    fixdir = os.environ.get("FIXINDEX_DIR")
    if not fixdir:
        print("FIXINDEX_DIR not set", file=sys.stderr)
        return 2
    if len(sys.argv) < 2:
        print("usage: golden_seed.py <out.jsonl>", file=sys.stderr)
        return 2
    out_path = sys.argv[1]

    fxmeta = load_fxmeta()
    files = sorted(glob.glob(os.path.join(fixdir, "[0-9]*.md")))
    seeded = 0
    skipped = 0
    cases = []
    for fp in files:
        fid = os.path.basename(fp)[:4]
        txt = open(fp, encoding="utf-8").read()
        fm, body_start = fxmeta.parse_frontmatter_full(txt)

        status = str(fm.get("status") or "").strip().lower()
        if status == "superseded":
            skipped += 1
            continue

        symps = fm.get("symptoms") or []
        if not symps or not str(symps[0]).strip():
            skipped += 1
            continue

        body = txt[body_start:] if body_start < len(txt) else txt
        if not RULE_RE.search(body):
            skipped += 1
            continue

        # 該條目自身的 section keys（enumerate 語意，與 fxsearch.build_entries 一致）
        sec_count = len(list(fxmeta.iter_sections(txt, body_start)))
        expect_ids = [f"{fid}#{sn}" for sn in range(1, sec_count + 1)]

        cases.append({
            "id": f"g{seeded + 1:03d}",
            "query": str(symps[0]).strip(),
            "expect_ids": expect_ids,
            "expect_not": [],
            "src": "auto:rule-backfill",
        })
        seeded += 1

    with open(out_path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"seeded={seeded} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())