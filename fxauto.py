#!/usr/bin/env python3
"""
fxauto.py — shadow-mode fixindex entry generator.
Usage: echo '...' | fxauto.py --shadow   (preview)
       echo '...' | fxauto.py --commit   (write + re-index)
Input: lines in KEY: value format (SYMPTOM, ROOT, FIX, VERIFY)
"""

import sys, os, json, re, time, glob as _glob

FIXINDEX_DIR = os.environ.get('FIXINDEX_DIR',
    os.path.expanduser('~/.claude/projects/-Users-51mini/memory/fixes'))

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

def main():
    if len(sys.argv) < 2:
        print("usage: fxauto.py [--shadow|--commit]", file=sys.stderr)
        sys.exit(1)
    mode = sys.argv[1]

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

    fid = next_id()
    title = symps[0][:80]
    slug = slugify(f'{fid}-{title}'[:60])

    entry = build_entry(fid, title, symps, root, fix, verify, slug)

    if mode == '--shadow':
        print(json.dumps({'preview_lines': len(entry.split('\n')), 'first_5': entry[:300]}))
    else:
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        path = os.path.join(FIXINDEX_DIR, f'{fid}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        print(json.dumps({'created': path}))
        os.system(f'fixindex re-index 2>/dev/null')


if __name__ == '__main__':
    main()