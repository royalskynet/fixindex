#!/usr/bin/env python3
"""
fxmeta.py — fixindex frontmatter 單一解析權威（手寫，不依賴 PyYAML）
支援：dump / get / set / scan / normalize
"""
import sys, os, json, re, glob, collections

# ── parser ──────────────────────────────────────────────────────
RE_FM_DELIM = re.compile(r'^---\s*$')
RE_KV = re.compile(r'^([a-z_]+):\s*(.*)$')
RE_LIST_ITEM = re.compile(r'^\s*-\s+(.+)$')

def parse_frontmatter(text):
    """Return (dict, body_offset). Handles simple frontmatter including block lists."""
    lines = text.split('\n')
    if not lines or not RE_FM_DELIM.match(lines[0]):
        return {}, 0
    fm = {}
    current_key = None
    i = 1
    while i < len(lines):
        if RE_FM_DELIM.match(lines[i]):
            return fm, i + 1
        line = lines[i]
        stripped = line.strip()
        if stripped == '':
            # reset current key on blank line
            current_key = None
            i += 1
            continue
        kv = RE_KV.match(line)
        if kv:
            current_key = kv.group(1)
            val = kv.group(2).strip()
            if val in ('', '[]'):
                fm[current_key] = []
            elif val.startswith('[') and val.endswith(']'):
                inner = val[1:-1]
                items = [x.strip() for x in _split_inline(inner) if x.strip()]
                fm[current_key] = items
            else:
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                fm[current_key] = val
            i += 1
            continue
        # list item line
        li = RE_LIST_ITEM.match(line)
        if li and current_key:
            item = li.group(1).strip().strip('"\'')
            if current_key not in fm or not isinstance(fm[current_key], list):
                fm[current_key] = []
            fm[current_key].append(item)
            i += 1
            continue
        # unrecognized line – skip
        i += 1
    if i < len(lines) and RE_FM_DELIM.match(lines[i]):
        i += 1
    return fm, i


def parse_frontmatter_full(text):
    """Full frontmatter parser handling block lists correctly."""
    lines = text.split('\n')
    if not lines or not RE_FM_DELIM.match(lines[0]):
        return {}, 0
    fm = {}
    current_key = None
    i = 1
    while i < len(lines):
        if RE_FM_DELIM.match(lines[i]):
            return fm, i + 1
        line = lines[i]
        stripped = line.strip()
        if stripped == '':
            # empty line inside frontmatter — always reset current_key
            # next non-empty line with KV will set it; list items would fail without current_key
            current_key = None
            i += 1
            continue

        kv = RE_KV.match(line)
        if kv:
            current_key = kv.group(1)
            val = kv.group(2).strip()
            if val in ('', '[]'):
                fm[current_key] = []
            elif val.startswith('[') and val.endswith(']'):
                inner = val[1:-1]
                items = [x.strip().strip('"\'') for x in _split_inline(inner) if x.strip()]
                fm[current_key] = items
            else:
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                fm[current_key] = val
            i += 1
            continue

        li = RE_LIST_ITEM.match(line)  # match against original line (not stripped)
        if li and current_key:
            item = li.group(1).strip().strip('"\'')
            if current_key not in fm or not isinstance(fm[current_key], list):
                fm[current_key] = []
            fm[current_key].append(item)
            i += 1
            continue

        # not a recognized line — skip, don't reset current_key
        i += 1

    if i < len(lines) and RE_FM_DELIM.match(lines[i]):
        i += 1
    return fm, i


def _split_inline(s):
    """Split inline list contents like: 'a', 'b, c', d"""
    parts = []
    current = ''
    in_quote = False
    for ch in s:
        if ch == '"' or ch == "'":
            in_quote = not in_quote
            current += ch
        elif ch == ',' and not in_quote:
            parts.append(current)
            current = ''
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return parts


def _needs_yaml_quotes(s: str) -> bool:
    """Return True if string s needs quoting in YAML output."""
    if s == '':
        return True
    # leading/trailing whitespace
    if s != s.strip():
        return True
    # starts with digit and all digits (leading zero -> octal, all digits -> int)
    if s.isdigit():
        return True
    # starts with 0 and all digits (covers 0045 etc.)
    if s.startswith('0') and s.isdigit():
        return True
    # contains ': ' (colon-space) or ends with ':'
    if ': ' in s or s.endswith(':'):
        return True
    # contains '#'
    if '#' in s:
        return True
    # contains quotes
    if '"' in s or "'" in s:
        return True
    # starts with YAML indicator characters
    if s and s[0] in '-?:,[]{}&#*!|>%@`':
        return True
    # contains backslash
    if '\\\\' in s:
        return True
    return False


def _yaml_quote(s: str) -> str:
    """Return YAML-safe quoted string for s. Assumes _needs_yaml_quotes(s) is True."""
    has_double = '"' in s
    has_single = "'" in s
    if has_double and not has_single:
        # use single quotes, escape internal single quotes by doubling
        return "'" + s.replace("'", "''") + "'"
    if has_single and not has_double:
        # use double quotes, escape internal double quotes
        return '"' + s.replace('"', '\\\\"') + '"'
    if has_double and has_single:
        # both present: use single quotes, escape internal single quotes
        return "'" + s.replace("'", "''") + "'"
    # no quotes inside: prefer double quotes for backslash handling
    if '\\\\' in s:
        return '"' + s.replace('"', '\\\\"') + '"'
    # default: double quotes
    return '"' + s + '"'


# ── 已知欄位定義 ────────────────────────────────────────────
KNOWN_LISTS = {'symptoms', 'tags', 'related', 'supersedes'}
KNOWN_SCALARS = {'id', 'slug', 'type', 'title', 'status'}
ALLOWED_STATUS = {'active', 'superseded', 'draft', 'wontfix', 'archived'}
STATUS_MAP = {
    'active': 'active', 'in-progress': 'active', 'open': 'active',
    'partial-fix': 'active', 'fixed': 'active', 'resolved': 'active', 'done': 'active',
    'superseded': 'superseded',
    'draft': 'draft',
    'wontfix': 'wontfix', 'rejected': 'wontfix',
    'archived': 'archived',
}
ORDER = ['id', 'slug', 'type', 'title', 'tags', 'symptoms', 'status', 'supersedes', 'related']


# ── core operations ──────────────────────────────────────────

def read_file(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def get_sections(text, body_start):
    """Parse body into sections based on ## §N headings"""
    body = text[body_start:]
    sections = []
    current = {'heading': '', 'content': ''}
    for line in body.split('\n'):
        m = re.match(r'^##\s*§(\d+)\s*(.*)', line)
        if m:
            if current['heading']:
                sections.append(current)
            current = {'heading': f'§{m.group(1)} {m.group(2).strip()}', 'content': line + '\n'}
        else:
            current['content'] += line + '\n'
    if current.get('content', '').strip():
        sections.append(current)
    return sections


def scan(dir_path):
    """JSONL output: one JSON per fix file with all metadata"""
    for f in sorted(glob.glob(os.path.join(dir_path, '[0-9]*.md'))):
        txt = read_file(f)
        fm, body_start = parse_frontmatter_full(txt)
        sections = get_sections(txt, body_start)
        fm['_file'] = os.path.basename(f)
        fm['_sections'] = [s['heading'] for s in sections]
        print(json.dumps(fm, ensure_ascii=False))


def normalize_file(path, dry=True):
    """Normalize frontmatter: block lists, zero-pad, status 5-value"""
    txt = read_file(path)
    fm, body_start = parse_frontmatter_full(txt)

    # canonicalize
    for key in fm:
        if key in KNOWN_LISTS:
            if not isinstance(fm[key], list):
                fm[key] = [str(fm[key])] if fm[key] else []
            # stringify items, strip quotes
            fm[key] = [str(v).strip().strip('"').strip("'") for v in fm[key] if str(v).strip()]
        elif key == 'id':
            fm[key] = str(fm[key]).zfill(4)
        elif key == 'status':
            st = str(fm[key]).strip()
            fm[key] = STATUS_MAP.get(st, 'active')

    # Build canonical frontmatter block
    new_fm = '---\n'
    for k in ORDER:
        if k not in fm:
            continue
        v = fm[k]
        if k in KNOWN_LISTS:
            if not v:
                new_fm += f'{k}: []\n'
            else:
                new_fm += f'{k}:\n'
                for item in v:
                    if _needs_yaml_quotes(item):
                        new_fm += f'  - {_yaml_quote(item)}\n'
                    else:
                        new_fm += f'  - {item}\n'
        else:
            new_fm += f'{k}: {v}\n'
    # non-order fields (if any)
    for k, v in fm.items():
        if k in ORDER or k.startswith('_'):
            continue
        if isinstance(v, list):
            new_fm += f'{k}:\n'
            for item in v:
                if _needs_yaml_quotes(item):
                    new_fm += f'  - {_yaml_quote(item)}\n'
                else:
                    new_fm += f'  - {item}\n'
        else:
            new_fm += f'{k}: {v}\n'
    new_fm += '---\n'

    # keep body as-is
    body = txt if body_start == 0 else '\n'.join(txt.split('\n')[body_start:])

    new_txt = new_fm + body
    if new_txt != txt:
        if not dry:
            write_file(path, new_txt)
        return {'file': os.path.basename(path), 'changed': True}
    return {'file': os.path.basename(path), 'changed': False}


# ── CLI ───────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("usage: fxmeta.py <dump|get|set|scan|normalize> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'dump':
        path = sys.argv[2]
        txt = read_file(path)
        fm, body_start = parse_frontmatter_full(txt)
        print(json.dumps(fm, ensure_ascii=False))

    elif cmd == 'get':
        path, field = sys.argv[2], sys.argv[3]
        txt = read_file(path)
        fm, _ = parse_frontmatter_full(txt)
        val = fm.get(field, '')
        if isinstance(val, list):
            print(json.dumps(val, ensure_ascii=False))
        else:
            print(val)

    elif cmd == 'set':
        path = sys.argv[2]
        pairs = sys.argv[3:]
        txt = read_file(path)
        fm, body_start = parse_frontmatter_full(txt)
        for p in pairs:
            k, v = p.split('=', 1)
            fm[k] = v
        # Rebuild full file
        body = '\n'.join(txt.split('\n')[body_start:])
        new_txt = '---\n'
        for k in ORDER:
            if k in fm:
                new_txt += f'{k}: {fm[k]}\n'
        new_txt += '---\n' + body
        write_file(path, new_txt)

    elif cmd == 'scan':
        dir_path = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('FIXINDEX_DIR', '')
        scan(dir_path)

    elif cmd == 'normalize':
        path = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('FIXINDEX_DIR', '')
        dry = '--no-dry' not in sys.argv
        if os.path.isdir(path):
            results = [normalize_file(f, dry=dry) for f in sorted(glob.glob(os.path.join(path, '[0-9]*.md')))]
            changed = [r for r in results if r['changed']]
            total = len(results)
            print(json.dumps({'total': total, 'changed': len(changed), 'files': [r['file'] for r in changed]}))
        else:
            r = normalize_file(path, dry=dry)
            print(json.dumps(r))

    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    import os as _os
    KNOWN_LISTS = KNOWN_LISTS = KNOWN_LISTS
    dir = os
    main()