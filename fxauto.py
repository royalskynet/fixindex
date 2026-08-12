#!/usr/bin/env python3
"""
fxauto.py — shadow-mode fixindex entry generator with de-individuation.
Usage: echo '...' | fxauto.py --shadow       (preview + dedup check)
       echo '...' | fxauto.py --commit       (write/supersede + re-index)
Input: lines in KEY: value format (SYMPTOM, ROOT, FIX, VERIFY)

去個案化 (借鏡 claude-mem-lite auto-dedup / supersede):
  - 建檔前先比對既有條目標題, 新經驗關鍵詞 (tgt ⊆ ts) 判定為重複經驗
  - 重複時取代舊條目 (保留線索, 少走彎路)
"""

import sys, os, json, re, glob as _glob
import fxmeta

FIXINDEX_DIR = os.environ.get('FIXINDEX_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixes'))


def next_id():
    files = sorted(_glob.glob(os.path.join(FIXINDEX_DIR, '[0-9]*.md')))
    if not files:
        return '0001'
    last = os.path.basename(files[-1])[:4]
    return f'{int(last) + 1:04d}'


def slugify(text):
    import unicodedata
    s = unicodedata.normalize('NFKD', text.lower())
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60]


def _title_tokens(text):
    """Split title into tokens (reuse fxsearch.tokenize for CJK awareness)."""
    try:
        import fxsearch
        return set(fxsearch.tokenize(text))
    except Exception:
        norm = re.sub(r'[\s，。,.!?、:：;；()（）\[\]{}"\'`~\-—]+', '', text.lower())
        return {norm}


def find_duplicate(title):
    """Return (fid, overlap_ratio) if an existing title contains ALL tokens of
    the new title (tgt ⊆ ts) and shared-token ratio is high.

    Dedup 直覺（對齊 '不記個案'）：新經驗的關鍵詞若都已在某舊條目標題出現過
    （tgt ⊆ ts），視為重複經驗, 回傳舊條目供 supersede 取代。
    """
    import glob as _glob
    files = sorted(_glob.glob(os.path.join(FIXINDEX_DIR, '[0-9]*.md')))
    tgt = _title_tokens(title)
    if not tgt:
        return None
    best = None
    for fp in files:
        try:
            with open(fp) as f:
                txt = f.read()
        except Exception:
            continue
        fm, _ = fxmeta.parse_frontmatter_full(txt)
        t = fm.get('title') or os.path.basename(fp)
        ts = _title_tokens(str(t))
        if not ts:
            continue
        if tgt <= ts:
            overlap = len(tgt) / len(ts)   # 新詞佔舊標題比例, 越高越像
            if best is None or overlap > best[1]:
                best = (os.path.basename(fp)[:4], round(overlap, 2))
    return best


def build_entry(fid, title, symptoms, root, fix, verify, slug):
    parts = []
    parts.append('---')
    parts.append(f'id: {fid}')
    parts.append(f'slug: {slug}')
    parts.append(f'title: {title}')
    parts.append('tags:\n  - auto\n  - shadow')
    parts.append('symptoms:')
    for s in symptoms:
        parts.append(f'  - {s}')
    parts.append('status: active')
    parts.append('supersedes: []')
    parts.append('related: []')
    parts.append('---')
    parts.append('')
    parts.append(f'# {fid} {title}')
    parts.append('')
    parts.append('## §1 Symptom')
    parts.append('')
    parts.append('; '.join(symptoms))
    parts.append('')
    parts.append('## §2 Root cause')
    parts.append('')
    parts.append(root)
    parts.append('')
    parts.append('## §3 Fix')
    parts.append('')
    parts.append(fix)
    parts.append('')
    parts.append('## §4 Verify')
    parts.append('')
    parts.append(verify)
    return '\n'.join(parts) + '\n'


def _run_index(cmd, *args, **extra):
    """Run a fixindex subcommand bound to THIS FIXINDEX_DIR (so sandbox tests
    don't leak into the real library). Uses the fixindex next to this file."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixindex')
    if not os.path.exists(script):
        script = 'fixindex'  # fall back to PATH
    env = dict(os.environ, FIXINDEX_DIR=FIXINDEX_DIR)
    return os.system(f'FIXINDEX_DIR={env["FIXINDEX_DIR"]} "{script}" {cmd}' + ('' if cmd.startswith('re-index') else ' >/dev/null 2>&1'))


def main():
    args = sys.argv[1:]
    mode = None
    title_override = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--title' and i + 1 < len(args):
            title_override = args[i + 1]
            i += 1
        elif a in ('--shadow', '--commit'):
            mode = a
        i += 1
    if not mode:
        print("usage: fxauto.py [--shadow|--commit] [--title T]", file=sys.stderr)
        sys.exit(1)

    fields = {}
    for line in sys.stdin:
        m = re.match(r'^([A-Z]+):\s*(.+)', line.strip())
        if m:
            fields[m.group(1).lower()] = m.group(2).strip()

    sympt = fields.get('symptom', '')
    root = fields.get('root', 'untraced')
    fix = fields.get('fix', 'applied')
    verify = fields.get('verify', 'verified')

    if not sympt:
        print("SYMPTOM required", file=sys.stderr)
        sys.exit(1)

    symps = [s.strip() for s in sympt.split(';') if s.strip()]
    if not symps:
        symps = [sympt.strip()]

    title = (title_override or symps[0])[:80]
    dup = find_duplicate(title)

    if mode == '--shadow':
        payload = {'preview_lines': len(build_entry(next_id(), title, symps, root, fix, verify, '').split('\n'))}
        if dup:
            payload['dedup'] = {'supersedes': dup[0], 'overlap': round(dup[1], 2)}
        else:
            payload['dedup'] = None
        print(json.dumps(payload))
        return

    if dup:
        # 去個案化：取代舊條目, 不創重複檔
        old_id = dup[0]
        new_id = next_id()
        slug = slugify(f'{new_id}-{title}'[:60])
        entry = build_entry(new_id, title, symps, root, fix, verify, slug)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        path = os.path.join(FIXINDEX_DIR, f'{new_id}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        os.system(f'fixindex supersede {old_id} {new_id} >/dev/null 2>&1')
        print(json.dumps({'created': path, 'dedup': True, 'supersedes': old_id}))
    else:
        fid = next_id()
        slug = slugify(f'{fid}-{title}'[:60])
        entry = build_entry(fid, title, symps, root, fix, verify, slug)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        path = os.path.join(FIXINDEX_DIR, f'{fid}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        print(json.dumps({'created': path, 'dedup': False}))
        os.system(f'fixindex re-index 2>/dev/null')


if __name__ == '__main__':
    main()