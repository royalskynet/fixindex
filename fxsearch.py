#!/usr/bin/env python3
"""fxsearch.py — BM25 retrieval over fixindex entries with section-level indexing."""
import sys, os, json, re, math, collections, glob

# ── tokenizer ──
def tokenize(text):
    out = []
    buf = ''
    for ch in text:
        cp = ord(ch)
        is_cjk = 0x4e00 <= cp <= 0x9fff or 0x3040 <= cp <= 0x30ff
        if is_cjk:
            if buf:
                out.append(buf.lower())
                buf = ''
            out.append(ch)
        elif ch.isalnum() or ch in '._/@-:#':
            buf += ch.lower()
        else:
            if buf:
                out.append(buf)
                buf = ''
    if buf:
        out.append(buf.lower())
    return [t for t in out if t]

# ── BM25 ──
K1, B = 1.2, 0.75

class BM25Engine:
    def __init__(self, docs):
        self.docs = docs
        self.n = len(docs)
        self.dls = [len(d['tokens']) for d in docs]
        self.avgdl = sum(self.dls) / max(self.n, 1)
        self.tfmaps = [collections.Counter(d['tokens']) for d in docs]
        self.df = collections.Counter()
        for tf in self.tfmaps:
            for t in tf:
                self.df[t] += 1

    def idf(self, t):
        df = self.df.get(t, 0)
        return max(0.5, math.log((self.n - df + 0.5) / (df + 0.5) + 1.0))

    def score(self, i, qtoks):
        dl = self.dls[i]
        s = 0.0
        tf = self.tfmaps[i]
        for t in qtoks:
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf(t) * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / max(self.avgdl, 1)))
        return s

    def search(self, query, limit=8):
        qt = set(tokenize(query))
        scores = [(i, self.score(i, qt)) for i in range(self.n)]
        return sorted([(i, s) for i, s in scores if s > 0], key=lambda x: -x[1])[:limit * 2]

# ── simple fm parser ──
RE_KV = re.compile(r'^([a-z_]+):\s*(.*)$')
def parse_fm(path):
    with open(path) as f:
        txt = f.read()
    fm = {}
    cur = None
    for line in txt.split('\n'):
        s = line.strip()
        if s == '---':
            if not fm:
                continue
            break
        if not fm:
            continue
        if s == '':
            cur = None
            continue
        m = RE_KV.match(line)
        if m:
            cur = m.group(1)
            v = m.group(2).strip()
            fm[cur] = v if v and not v.startswith('[') else []
        elif cur and re.match(r'^\s*-\s+', s):
            item = re.sub(r'^\s*-\s+', '', s).strip().strip('"')
            if not isinstance(fm.get(cur), list):
                fm[cur] = []
            fm[cur].append(item)
    return fm

# ── entry builder ──
def build_entries(fixdir):
    blurb_path = os.path.join(fixdir, '.blurbs.jsonl')
    blurbs = {}
    if os.path.exists(blurb_path):
        for line in open(blurb_path):
            try:
                j = json.loads(line)
                blurbs[j['key']] = j
            except:
                pass
    entries = []
    files = sorted(glob.glob(os.path.join(fixdir, '[0-9]*.md')))
    for fp in files:
        fn = os.path.basename(fp)
        fid = fn[:4]
        fm = parse_fm(fp)
        with open(fp) as f:
            txt = f.read()
        parts = txt.split('---', 2)
        body = parts[2] if len(parts) >= 3 else txt
        # sections
        secs = []
        cur_h = cur_b = ''
        in_sec = False
        for line in body.split('\n'):
            if line.startswith('## §'):
                if in_sec:
                    secs.append((cur_h, cur_b.strip()))
                cur_h = line
                cur_b = line + '\n'
                in_sec = True
            elif in_sec:
                cur_b += line + '\n'
        if in_sec:
            secs.append((cur_h, cur_b.strip()))

        for sn, (hd, cont) in enumerate(secs):
            key = f'{fid}#{sn + 1}'
            m = re.search(r'##\s*§\d+\s+(.+)', hd)
            heading = m.group(1).strip() if m else '(untitled)'
            bi = blurbs.get(key, {})
            toks = []
            # heading 2x
            toks.extend(tokenize(heading))
            to = tokenize(heading)
            toks += to + to
            # symptoms 3x
            for sx in fm.get('symptoms', []):
                ts = tokenize(sx)
                toks.extend(ts * 3)
            # tags 1.5x
            for t in fm.get('tags', []):
                ts = tokenize(t)
                toks.extend(ts)
                toks.extend(ts)
            # vocab 1.8x
            for v in bi.get('vocab', []):
                ts = tokenize(v)
                toks.extend(ts)
                toks.extend(ts)
            # blurb 0.8x
            ts = tokenize(bi.get('blurb', ''))
            toks.extend(ts)
            # body 1x
            toks.extend(tokenize(cont))
            entries.append({
                'key': key,
                'file': fn,
                'section': f'§{sn + 1}',
                'heading': heading,
                'tokens': toks,
            })
    return entries


def main():
    if len(sys.argv) < 2:
        print("usage: fxsearch.py <query> [--limit N] [--all] [--json]", file=sys.stderr)
        sys.exit(1)
    # Walk flags before positional
    args = sys.argv[1:]
    limit = 8
    json_out = False
    q = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--json':
            json_out = True
        elif a == '--limit' and i+1 < len(args):
            limit = int(args[i+1])
            i += 1
        elif not a.startswith('--'):
            if q is None:
                q = a
        i += 1
    if q is None:
        print("usage: fxsearch.py <query> [--limit N] [--json]", file=sys.stderr)
        sys.exit(1)
    fixdir = os.environ.get('FIXINDEX_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixes')
    entries = build_entries(fixdir)
    if not entries:
        if json_out:
            print(json.dumps({'query': q, 'hits': []}))
        else:
            print("(no entries)")
        return
    bm = BM25Engine(entries)
    results = bm.search(q, limit=limit)
    # group by file
    seen = {}
    top = []
    for i, s in results:
        e = entries[i]
        fid = e['file'][:4]
        if fid in seen:
            continue
        seen[fid] = True
        top.append((e, s))
        if len(top) >= limit:
            break
    if json_out:
        hits = [{'key': e['key'], 'file': e['file'], 'section': e['section'],
                 'heading': e['heading'], 'score': round(s, 3)} for e, s in top]
        print(json.dumps({'query': q, 'hits': hits}, ensure_ascii=False))
    else:
        for e, s in top:
            print(f"  {e['key']:<8} {e['section']:<5} ({s:4.2f})  {e['heading']}")
        print(f"\nmatched {len(results)} sections; showing top {len(top)}")


if __name__ == '__main__':
    main()