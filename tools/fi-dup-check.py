#!/usr/bin/env python3
"""同一輪新增的條目兩兩比標題，太像就 FAIL。

為什麼：/fi 的 agent 一條一條查重，同一輪自己剛寫出去的條目它查不到
（2026-11-12：一輪寫 17 條，實際只有 6 個主題，事後再開 amend 單收斂）。
查重只能擋「跟庫裡既有的重複」，擋不到「跟自己這輪重複」。

用法：fi-dup-check.py <id>...        # 退出碼 0 無重複、1 有重複
     fi-dup-check.py --threshold 0.6 <id>...
相似度＝標題 token 的 Jaccard，分詞用 fxsearch.tokenize（與檢索同一套；
difflib 對中文逐字比，「快取失效」與「快取命中」會算很像，不能用）。
"""
import os, sys, glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fxsearch

DEFAULT_THRESHOLD = 0.6
# 每條標題都有的結構詞，留著會讓兩條無關條目看起來很像
STOP = {'的', '會', '要', '不', '是', '在', '用', '把', '被', '和', '與', '後', '前', '時'}


def fixdir():
    return os.environ.get('FIXINDEX_DIR') or os.path.expanduser('~/dev/fix-store/fixes')


def title_of(fid):
    hits = glob.glob(os.path.join(fixdir(), f'{fid}-*.md'))
    if not hits:
        return None
    with open(hits[0], encoding='utf-8') as f:
        for ln in f:
            if ln.startswith('title:'):
                return ln.split(':', 1)[1].strip().strip('"\'')
            if ln.startswith('## '):
                break
    return ''


def toks(title):
    return {t for t in fxsearch.tokenize(title or '') if t not in STOP and len(t) > 1}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    args = sys.argv[1:]
    th = DEFAULT_THRESHOLD
    ids = []
    i = 0
    while i < len(args):
        if args[i] == '--threshold' and i + 1 < len(args):
            th = float(args[i + 1]); i += 1
        elif not args[i].startswith('--'):
            ids.append(args[i])
        i += 1
    if not ids:
        print('usage: fi-dup-check.py [--threshold F] <id>...', file=sys.stderr)
        sys.exit(2)

    titles = {}
    missing = []
    for fid in ids:
        t = title_of(fid)
        if t is None:
            missing.append(fid)
        else:
            titles[fid] = t
    if missing:
        print('找不到條目：' + ' '.join(missing), file=sys.stderr)
        sys.exit(2)

    dups = []
    keys = list(titles)
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            s = jaccard(toks(titles[keys[a]]), toks(titles[keys[b]]))
            if s >= th:
                dups.append((keys[a], keys[b], s))
    if dups:
        for x, y, s in sorted(dups, key=lambda d: -d[2]):
            print(f'DUP {s:.2f}  {x} {titles[x]}\n          {y} {titles[y]}')
        print(f'\n同輪重複 {len(dups)} 組（門檻 {th}）：合併成一條，或用 fixindex supersede 標掉其中一條。',
              file=sys.stderr)
        sys.exit(1)
    print(f'no same-round duplicates ({len(ids)} ids, threshold {th})')


if __name__ == '__main__':
    main()
