#!/usr/bin/env python3
"""
fxmeta.py — fixindex frontmatter 單一解析權威（手寫，不依賴 PyYAML）
支援：dump / get / set / scan / normalize / strip_tags
      section / mark / outcome / audit（§4 trust metadata 唯一權威）
"""
import sys, os, json, re, glob, datetime, tempfile

# ── parser ──────────────────────────────────────────────────────
RE_FM_DELIM = re.compile(r'^---\s*$')
RE_KV = re.compile(r'^([a-z_]+):\s*(.*)$')
RE_LIST_ITEM = re.compile(r'^\s*-\s+(.+)$')

def parse_frontmatter(text):
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
        li = RE_LIST_ITEM.match(line)
        if li and current_key:
            item = li.group(1).strip().strip('"\'')
            if current_key not in fm or not isinstance(fm[current_key], list):
                fm[current_key] = []
            fm[current_key].append(item)
            i += 1
            continue
        i += 1
    if i < len(lines) and RE_FM_DELIM.match(lines[i]):
        i += 1
    return fm, i


def parse_frontmatter_full(text):
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
        li = RE_LIST_ITEM.match(line)
        if li and current_key:
            item = li.group(1).strip().strip('"\'')
            if current_key not in fm or not isinstance(fm[current_key], list):
                fm[current_key] = []
            fm[current_key].append(item)
            i += 1
            continue
        i += 1
    if i < len(lines) and RE_FM_DELIM.match(lines[i]):
        i += 1
    return fm, i


def _split_inline(s):
    parts, cur, in_q = [], '', False
    for ch in s:
        if ch in ('"', "'"):
            in_q = not in_q
            cur += ch
        elif ch == ',' and not in_q:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _needs_yaml_quotes(s):
    if not isinstance(s, str):
        return True
    if s == '' or s != s.strip():
        return True
    if s.isdigit() or (s.startswith('0') and s.isdigit()):
        return True
    if ': ' in s or s.endswith(':') or '#' in s:
        return True
    if '"' in s or "'" in s or '\\' in s:
        return True
    if s and s[0] in '-?:,[]{}&#*!|>%@`':
        return True
    return False


def _yaml_quote(s):
    s = str(s)
    hs, hd = "'" in s, '"' in s
    if hs and hd:
        return "'" + s.replace("'", "''") + "'"
    if hs:
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return "'" + s.replace("'", "''") + "'" if not hd else s


# ── 已知欄位定義 ────────────────────────────────────────────
KNOWN_LISTS = {'symptoms', 'tags', 'related', 'supersedes'}
KNOWN_SCALARS = {'id', 'slug', 'type', 'title', 'status'}
ALLOWED_STATUS = {'active', 'superseded', 'draft', 'wontfix', 'archived'}
STATUS_MAP = {
    'active': 'active', 'in-progress': 'active', 'open': 'active',
    'partial-fix': 'active', 'fixed': 'active', 'resolved': 'active', 'done': 'active',
    'superseded': 'superseded', 'draft': 'draft', 'wontfix': 'wontfix',
    'rejected': 'wontfix', 'archived': 'archived',
}
ORDER = ['id', 'slug', 'type', 'title', 'tags', 'symptoms', 'status', 'supersedes', 'related']


# ─── §4 section-level trust metadata（唯一權威）──────────────
VALID_STATES = {'unverified', 'verified', 'stale', 'blocked', 'superseded'}
VALID_OUTCOMES = {'helpful', 'irrelevant', 'failed'}
SECTION_KEY = re.compile(r'^(\d{4})#(\d+)$')
SECTION_HEAD = re.compile(r'^##\s*§(\d+)\s*(.*)$')
BOLD_FIELD = re.compile(r'^\*\*([A-Za-z][A-Za-z- ]*?):\*\*\s*(.*)$')
TRUST_LABELS = {'State': 'state', 'Evidence': 'evidence',
                'Last verified': 'last_verified', 'Last reviewed': 'last_reviewed',
                'Outcome': 'outcome'}


def _valid_iso(s):
    if not isinstance(s, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', s.strip()):
        return False
    try:
        datetime.date.fromisoformat(s.strip())
        return True
    except ValueError:
        return False


def parse_section(section_text):
    """Parse section body → {'trust': {...}, 'unknown': [...]}. Never raises."""
    trust, unknown = {}, []
    for ln in section_text.split('\n'):
        st = ln.strip()
        m = BOLD_FIELD.match(st)
        if not m:
            continue
        label, val = m.group(1).strip(), m.group(2).strip()
        key = TRUST_LABELS.get(label)
        if key is None:
            unknown.append(label)
        elif key in trust:
            continue
        elif key in ('last_verified', 'last_reviewed'):
            trust[key] = val
        elif key == 'outcome':
            parsed = {}
            for pair in re.split(r'\s+', val):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    if k in VALID_OUTCOMES and v.isdigit():
                        parsed[k] = int(v)
            trust[key] = parsed
        else:
            trust[key] = val
    return {'trust': trust, 'unknown': unknown}


def section_summary(section_text):
    """(state, last_verified, outcome, evidence) for badge/JSON. Legacy → ('unverified', None, {}, '')."""
    t = parse_section(section_text)['trust']
    state = t.get('state') or 'unverified'
    if state not in VALID_STATES:
        state = 'unverified'
    last = t.get('last_verified') or t.get('last_reviewed')
    outcome = t.get('outcome') or {}
    ev = t.get('evidence', '')
    return state, last, outcome, ev


def iter_sections(text, body_start=0):
    """Yield (secnum, heading, body) for each ## §N; body if body_start given slices text."""
    if body_start >= len(text):
        body = text
    else:
        body = text[body_start:]
    cur_num, cur_head, cur_parts = None, '', []
    for ln in body.split('\n'):
        m = SECTION_HEAD.match(ln.strip())
        if m:
            if cur_num is not None:
                yield cur_num, cur_head, '\n'.join(cur_parts)
            cur_num, cur_head = int(m.group(1)), m.group(2).strip()
            cur_parts = [ln]
        elif cur_num is not None:
            cur_parts.append(ln)
    if cur_num is not None:
        yield cur_num, cur_head, '\n'.join(cur_parts)


def parse_key(key):
    """'0553#1' → (553, 1). Raises ValueError."""
    m = SECTION_KEY.match((key or '').strip())
    if not m:
        raise ValueError(f"invalid section key '{key}' (expected NNNN#N, e.g. 0553#1)")
    return int(m.group(1)), int(m.group(2))


def find_section(num, text):
    """Split text at `## §num` heading.  Returns (header_lines, section_lines,
    trailer_lines) or None if the section number isn't found."""
    lines = text.split('\n')
    start = None
    for i, ln in enumerate(lines):
        m = SECTION_HEAD.match(ln.strip())
        if m and int(m.group(1)) == num:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if SECTION_HEAD.match(lines[i].strip()):
            end = i
            break
    return lines[:start], lines[start:end], lines[end:]


def _atomic_write(path, content):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.fxmeta-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def mark(path, key, state, evidence=None, date=None, reason=None):
    """Write State/Evidence/Last verified|reviewed into section KEY. Returns result dict.

    Never touches frontmatter or other sections; atomic; read-back verified."""
    fid, secnum = parse_key(key)
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    fm, _ = parse_frontmatter_full(txt)
    fm_id = str(fm.get('id') or '').strip() or os.path.basename(path)[:4]
    if str(fm_id).zfill(4) != f'{fid:04d}':
        return {'error': f'id mismatch: frontmatter {str(fm_id).zfill(4)} != key {fid:04d}#{secnum}', 'key': key}

    state = (state or '').strip() or 'unverified'
    if state not in VALID_STATES:
        return {'error': f"invalid state '{state}' (allowed: {', '.join(sorted(VALID_STATES))})", 'key': key}

    if state == 'verified':
        if not (evidence and str(evidence).strip()):
            return {'error': 'verified requires non-empty --evidence', 'key': key}
        if not (date and _valid_iso(date)):
            return {'error': 'verified requires valid ISO --date YYYY-MM-DD', 'key': key}
        evidence, date = str(evidence).strip(), str(date).strip()
    elif state in ('stale', 'blocked', 'superseded'):
        if not (reason and str(reason).strip()):
            return {'error': f"state '{state}' requires --reason", 'key': key}
        evidence, date = str(reason).strip(), None

    # locate section
    seg = find_section(secnum, txt)
    if seg is None:
        return {'error': f'section §{secnum} not found in {os.path.basename(path)}', 'key': key}
    header_lines, section_lines, trailer = seg

    is_insight = str(fm.get('type') or 'defect') == 'insight'
    date_label = 'Last reviewed' if is_insight else 'Last verified'

    want = {}
    if state != 'unverified' and state in VALID_STATES:
        want['State'] = state
    if evidence is not None:
        want['Evidence'] = evidence
    if date is not None:
        want[date_label] = date

    # separate the `## N` header line from the rest of the section
    head = section_lines[0]
    rest = section_lines[1:]
    keep = []
    for ln in rest:
        st = ln.strip()
        m = BOLD_FIELD.match(st)
        if m:
            k = TRUST_LABELS.get(m.group(1).strip())
            # drop any trust line we are about to set (or when unverified, drop all trust)
            if k in ('state', 'evidence', 'last_verified', 'last_reviewed') or m.group(1).strip() in TRUST_LABELS:
                if state == 'unverified' or m.group(1).strip() in want:
                    continue
        keep.append(ln)

    # canonical order: State, Evidence, Date
    ordered = []
    if 'State' in want:
        ordered.append(f'**State:** {want["State"]}')
    if 'Evidence' in want:
        ordered.append(f'**Evidence:** {want["Evidence"]}')
    if date is not None and date_label in want:
        ordered.append(f'**{date_label}:** {want[date_label]}')

    new_section = [head] + ordered + keep
    new_txt = '\n'.join(header_lines) + ('\n' if header_lines else '')
    new_txt += '\n'.join(new_section)
    if trailer:
        new_txt += '\n' + '\n'.join(trailer)
    if not txt.endswith('\n'):
        new_txt += '\n'

    _atomic_write(path, new_txt)

    # read-back verify
    rb = open(path, encoding='utf-8').read()
    seg2 = find_section(secnum, rb)
    ok = seg2 is not None and ('State' in want) == (any(
        BOLD_FIELD.match(ln.strip()) and TRUST_LABELS.get(BOLD_FIELD.match(ln.strip()).group(1).strip()) == 'state'
        for ln in seg2[1]))
    readback = {}
    if seg2 is not None:
        ss = parse_section('\n'.join(seg2[1]))
        readback = ss['trust']
    return {'ok': ok, 'key': key, 'state': state, 'evidence': evidence,
            'last_verified': date, 'readback': readback, 'path': path}


def outcome(path, key, which):
    """Increment the anonymous Outcome counter for section KEY. Returns dict."""
    fid, secnum = parse_key(key)
    which = (which or '').strip()
    if which not in VALID_OUTCOMES:
        return {'error': f"invalid outcome '{which}' (allowed: helpful|irrelevant|failed)", 'key': key}
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    seg = find_section(secnum, txt)
    if seg is None:
        return {'error': f'section §{secnum} not found', 'key': key}
    header_lines, section_lines, trailer = seg
    head = section_lines[0]
    rest = section_lines[1:]
    # current outcome (if any)
    cur = {}
    for ln in rest:
        m = BOLD_FIELD.match(ln.strip())
        if m and m.group(1).strip() == 'Outcome':
            for pair in re.split(r'\s+', m.group(2).strip()):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    if k in VALID_OUTCOMES and v.isdigit():
                        cur[k] = int(v)
    cur[which] = cur.get(which, 0) + 1
    out_str = ' '.join(f'{k}={cur.get(k, 0)}' for k in VALID_OUTCOMES)
    # remove old Outcome line and any trust lines we'll rewrite
    new_rest = []
    for ln in rest:
        m = BOLD_FIELD.match(ln.strip())
        if m and m.group(1).strip() == 'Outcome':
            continue
        new_rest.append(ln)
    # append the updated Outcome line after the body (canonical trailing trust block
    # would go here; but to avoid reordering body, append at the end of the section)
    new_section = [head] + new_rest + [f'**Outcome:** {out_str}']
    new_txt = '\n'.join(header_lines) + ('\n' if header_lines else '')
    new_txt += '\n'.join(new_section)
    if trailer:
        new_txt += '\n' + '\n'.join(trailer)
    if not txt.endswith('\n'):
        new_txt += '\n'
    _atomic_write(path, new_txt)
    return {'ok': True, 'key': key, 'outcome': cur, 'path': path}


def audit_section(section_text, num, heading):
    """One section's audit. Returns ({state,last,evidence,outcome,problems}, is_insight)."""
    p = parse_section(section_text)
    t = p['trust']
    problems = []
    state = t.get('state')
    if state is None:
        # legacy section: unverified by definition, NOT a quality problem
        state = 'unverified'
    elif state == 'verified':
        if not (t.get('evidence') and t.get('evidence').strip()):
            problems.append('verified but empty Evidence')
        lv = t.get('last_verified') or t.get('last_reviewed')
        if not (lv and _valid_iso(lv)):
            problems.append('verified but missing/invalid date')
    elif state in ('stale', 'blocked', 'superseded'):
        if not (t.get('evidence') and t.get('evidence').strip()):
            problems.append(f'{state} without Evidence (mark with --reason)')
    elif state not in VALID_STATES:
        problems.append(f"invalid State '{state}'")
    oc = t.get('outcome') or {}
    if any(v < 0 for v in oc.values()):
        problems.append('negative Outcome counter')
    return {'secnum': num, 'state': state, 'last': t.get('last_verified') or t.get('last_reviewed'),
            'evidence': t.get('evidence', ''), 'outcome': oc, 'problems': problems}


# ── core operations ──────────────────────────────────────────
def read_file(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def scan(dir_path):
    """JSONL output: one JSON per fix file with all metadata"""
    for f in sorted(glob.glob(os.path.join(dir_path, '[0-9]*.md'))):
        txt = read_file(f)
        fm, body_start = parse_frontmatter_full(txt)
        fm['_file'] = os.path.basename(f)
        fm['_sections'] = [h for n, h, b in iter_sections(txt, body_start)]
        print(json.dumps(fm, ensure_ascii=False))


def normalize_file(path, dry=True):
    """Normalize frontmatter: block lists, zero-pad, status 5-value"""
    txt = read_file(path)
    fm, body_start = parse_frontmatter_full(txt)

    for key in fm:
        if key in KNOWN_LISTS:
            if not isinstance(fm[key], list):
                fm[key] = [str(fm[key])] if fm[key] else []
            fm[key] = [str(v).strip().strip('"').strip("'") for v in fm[key] if str(v).strip()]
        elif key == 'id':
            fm[key] = str(fm[key]).zfill(4)
        elif key == 'status':
            st = str(fm[key]).strip()
            fm[key] = STATUS_MAP.get(st, 'active')

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
            sv = str(v)
            new_fm += f'{k}: {_yaml_quote(sv) if _needs_yaml_quotes(sv) else sv}\n'
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
            sv = str(v)
            new_fm += f'{k}: {_yaml_quote(sv) if _needs_yaml_quotes(sv) else sv}\n'
    new_fm += '---\n'

    body = txt if body_start == 0 else '\n'.join(txt.split('\n')[body_start:])
    new_txt = new_fm + body
    if new_txt != txt:
        if not dry:
            write_file(path, new_txt)
        return {'file': os.path.basename(path), 'changed': True}
    return {'file': os.path.basename(path), 'changed': False}


def strip_tags(path, drop, dry=True):
    """從 frontmatter tags 移除 vestigial tag（drop: 集合）。只動 tags 區段。"""
    drop = set(drop or [])
    txt = read_file(path)
    lines = txt.split('\n')
    starts = [i for i, ln in enumerate(lines) if ln.strip() == '---']
    if len(starts) < 2:
        return {'file': os.path.basename(path), 'changed': False, 'dropped': []}
    a, b = starts[0], starts[1]
    start = None
    for i in range(a + 1, b):
        if re.match(r'^tags:', lines[i]):
            start = i
            break
    if start is None:
        return {'file': os.path.basename(path), 'changed': False, 'dropped': []}
    headval = lines[start].split(':', 1)[1].strip()
    kept, dropped = [], []
    if headval.startswith('[') and headval.endswith(']'):
        inner = headval[1:-1]
        for x in [v.strip().strip('"\'') for v in inner.split(',') if v.strip()]:
            (dropped if x in drop else kept).append(x)
        block_tail = False
        idx = start + 1
        while idx < b and re.match(r'^\s*-\s+', lines[idx]):
            item = lines[idx].strip()[2:].strip().strip('"\'')
            (dropped if item in drop else kept).append(item)
            idx += 1
            block_tail = True
        end = idx if block_tail else start + 1
        new_lines = ['tags:'] + [f'  - {_yaml_quote(t) if _needs_yaml_quotes(t) else t}' for t in kept]
        if not kept:
            new_lines = ['tags: []']
    else:
        idx = start + 1
        while idx < b and re.match(r'^\s*-\s+', lines[idx]):
            item = lines[idx].strip()[2:].strip().strip('"\'')
            (dropped if item in drop else kept).append(item)
            idx += 1
        end = idx
        new_lines = ['tags:'] + [f'  - {_yaml_quote(t) if _needs_yaml_quotes(t) else t}' for t in kept]
        if not kept:
            new_lines = ['tags: []']
    if not dropped:
        return {'file': os.path.basename(path), 'changed': False, 'dropped': []}
    new_txt = '\n'.join(lines[:start] + new_lines + lines[end:])
    if new_txt != txt:
        if not dry:
            write_file(path, new_txt)
    return {'file': os.path.basename(path), 'changed': True, 'dropped': dropped}


# ── CLI ───────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("usage: fxmeta.py <dump|get|set|scan|normalize|strip_tags|section|mark|outcome|audit> ...", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'dump':
        path = sys.argv[2]
        txt = read_file(path)
        fm, _ = parse_frontmatter_full(txt)
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

    elif cmd == 'strip_tags':
        path = sys.argv[2]
        drop = [x.strip() for x in sys.argv[3].split(',') if x.strip()]
        dry = '--no-dry' not in sys.argv
        r = strip_tags(path, drop, dry=dry)
        print(json.dumps(r))

    elif cmd == 'section':
        # read-only section trust dump for a key: fxmeta.py section <path> <NNNN#N>
        path, key = sys.argv[2], sys.argv[3]
        _, secnum = parse_key(key)
        txt = read_file(path)
        seg = find_section(secnum, txt)
        if seg is None:
            print(json.dumps({'error': f'section §{secnum} not found'}))
        else:
            print(json.dumps({'secnum': secnum, 'body': '\n'.join(seg[1])}))

    elif cmd == 'mark':
        path, key, state = sys.argv[2], sys.argv[3], sys.argv[4]
        evidence = date = reason = None
        i = 5
        while i < len(sys.argv):
            a = sys.argv[i]
            if a == '--evidence' and i + 1 < len(sys.argv):
                evidence = sys.argv[i + 1]; i += 2
            elif a == '--date' and i + 1 < len(sys.argv):
                date = sys.argv[i + 1]; i += 2
            elif a == '--reason' and i + 1 < len(sys.argv):
                reason = sys.argv[i + 1]; i += 2
            else:
                i += 1
        r = mark(path, key, state, evidence=evidence, date=date, reason=reason)
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r.get('ok') else 2)

    elif cmd == 'outcome':
        path, key, which = sys.argv[2], sys.argv[3], sys.argv[4]
        r = outcome(path, key, which)
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r.get('ok') else 2)

    elif cmd == 'audit':
        path = sys.argv[2]
        as_json = '--json' in sys.argv
        txt = read_file(path)
        fm, body_start = parse_frontmatter_full(txt)
        secs = list(iter_sections(txt, body_start))
        issues = []
        for num, head, body in secs:
            a = audit_section(body, num, head)
            if a['problems']:
                issues.append({'key': f'{str(fm.get("id") or "")[:4]}#{num}', 'problems': a['problems']})
        nums = [n for n, _, _ in secs]
        dup = [n for n in set(nums) if nums.count(n) > 1]
        if dup:
            issues.append({'duplicate_section_numbers': sorted(dup)})
        rc = 2 if (not secs) else (1 if issues else 0)
        if as_json:
            print(json.dumps({'file': os.path.basename(path), 'sections': len(secs),
                              'duplicate_numbers': dup, 'issues': issues}, ensure_ascii=False))
        else:
            for p in issues:
                print(f"  ISSUE {p}")
            print(f"audit: {len(issues)} issue(s) across {len(secs)} section(s)")
        sys.exit(rc)

    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()