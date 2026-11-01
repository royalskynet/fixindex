#!/usr/bin/env python3
"""fxhot.py — 把近期跨 session 反覆命中的 T6 已知坑，在 SessionStart 先講。

借鏡 microsoft/TokenEconomizer micro-skills：事實要 >=3 個 session 確認才在開場注入，
之後沒再出現就自然退場。這裡的「確認」＝recall log 裡 layer=pitfall 命中的不同 session 數；
窗口外不再命中＝退場（衰減，不需要另寫反駁邏輯）。零 LLM 呼叫。
fail-open：任何錯誤只輸出空字串、exit 0。

用法：fxhot.py [--days 14] [--min-sessions 3] [--top 5]
      fxhot.py --report   各注入層「注入後下一次工具呼叫成功率」（outcome log，fixindex-pretool.js 寫）
環境：FIXINDEX_RECALL_LOG、FIXINDEX_PITFALLS 覆寫路徑（測試用）。
"""
import argparse, collections, datetime as dt, json, os, sys

HOME = os.path.expanduser('~')
RECALL_LOG = os.environ.get('FIXINDEX_RECALL_LOG', os.path.join(HOME, '.claude', 'logs', 'fixindex-recall.jsonl'))
PITFALLS = os.environ.get('FIXINDEX_PITFALLS', os.path.join(HOME, 'dev', 'fix-store', 'pitfalls.tsv'))
OUTCOME_LOG = os.environ.get('FIXINDEX_OUTCOME_LOG', RECALL_LOG[:-len('.jsonl')] + '-outcome.jsonl' if RECALL_LOG.endswith('.jsonl') else RECALL_LOG + '-outcome.jsonl')
ADVICE_MAX = 110


def advice_by_id(path):
    out = {}
    for line in open(path, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        cols = line.rstrip('\n').split('\t')
        if len(cols) >= 5 and cols[0].strip() not in out:  # 同 id 多列取第一列的 advice
            out[cols[0].strip()] = (cols[3].strip(), cols[4].strip())
    return out


def hot(now, days, min_sessions, top):
    cut = (now - dt.timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')
    sess = collections.defaultdict(set)
    for line in open(RECALL_LOG, encoding='utf-8'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get('layer') != 'pitfall' or str(r.get('ts', '')) < cut:
            continue
        for i in r.get('ids') or []:
            sess[i].add(r.get('session'))
    adv = advice_by_id(PITFALLS)
    ranked = sorted((i for i, s in sess.items() if len(s) >= min_sessions and i in adv),
                    key=lambda i: -len(sess[i]))[:top]
    return [(i, len(sess[i]), *adv[i]) for i in ranked]


def report(now, days):
    cut = (now - dt.timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')
    agg = collections.defaultdict(lambda: [0, 0])
    for line in open(OUTCOME_LOG, encoding='utf-8'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get('ts', '')) < cut:
            continue
        a = agg[f"{r.get('layer')}:{r.get('trigger')}"]
        a[0] += 1
        a[1] += bool(r.get('ok'))
    return sorted(((k, n, ok) for k, (n, ok) in agg.items()), key=lambda x: -x[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=14)
    ap.add_argument('--min-sessions', type=int, default=3)
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    if a.report:
        try:
            rows = report(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), a.days)
        except FileNotFoundError:
            rows = []
        print(f'注入後下一次工具呼叫成功率（近 {a.days} 天）:' if rows else '尚無 outcome 紀錄')
        for k, n, ok in rows:
            print(f'  {k:32s} {ok}/{n}  {ok * 100 // n}%')
        return 0
    try:
        rows = hot(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), a.days, a.min_sessions, a.top)
    except Exception:
        return 0
    if not rows:
        return 0
    print(f'hot-pitfalls（近 {a.days} 天跨 >={a.min_sessions} session 反覆撞到，動手前先避開）:')
    for i, n, action, advice in rows:
        tag = '必擋' if action == 'deny' else '提示'
        print(f'  [fix {i}] {tag}·{n}s  {advice[:ADVICE_MAX]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
