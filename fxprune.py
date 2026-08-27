#!/usr/bin/env python3
"""fixindex prune — 唯讀「遺忘候選」報告。只列檔，不刪、不改任何檔案。

判定（純規則、不呼 LLM、不做語意判斷）——一個條目同時滿足三項才會入列：
  1. body 找不到 `**Rule:**` 行（沒有可泛化的規則）
  2. 只有 1 個 `## §` 段落（從沒被重複命中／累積過證據）
  3. frontmatter `status: active`（未被 supersede / 封存）

Usage:
  fixindex prune                每行 `<id>  <title>  <reason>`
  fixindex prune --json         單行 JSON list
兩者結尾都固定印：prune 只列候選，不刪檔。人工確認後用 fixindex supersede 或手動刪除。
"""
import sys, os, json, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fxmeta


def is_active(fm):
    """status 預設 active；只有明確非 active 才排除。"""
    s = str(fm.get('status') or 'active').strip().lower()
    return s == 'active'


def candidates(fixdir):
    """回傳 list of (id, title, reason)。純規則、無副作用。"""
    out = []
    for fp in sorted(glob.glob(os.path.join(fixdir, '[0-9]*.md'))):
        fid = os.path.basename(fp)[:4]
        try:
            txt = open(fp, encoding='utf-8').read()
        except Exception:
            continue
        fm, body_start = fxmeta.parse_frontmatter_full(txt)
        if not fm:
            continue
        if not is_active(fm):
            continue
        title = str(fm.get('title') or '').strip()
        body = txt[body_start:] if body_start else txt
        has_rule = '**Rule:**' in body
        # 數 `## §N` 段落標題（body 內）
        n_sec = len([ln for ln in body.splitlines() if ln.startswith('## §')])
        reasons = []
        if not has_rule:
            reasons.append('no Rule')
        if n_sec <= 1:
            reasons.append('single-section')
        if reasons:
            out.append((fid, title, '; '.join(reasons)))
    return out


def main():
    fixdir = os.environ.get('FIXINDEX_DIR') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'fixes')
    json_out = '--json' in sys.argv
    rows = candidates(fixdir)
    if json_out:
        print(json.dumps([{'id': i, 'title': t, 'reason': r} for i, t, r in rows],
                         ensure_ascii=False))
    else:
        for i, t, r in rows:
            print(f'{i}  {t}  {r}')
    print('prune 只列候選，不刪檔。人工確認後用 fixindex supersede 或手動刪除。',
          file=sys.stderr)


if __name__ == '__main__':
    main()