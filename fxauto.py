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

import sys, os, json, re, subprocess, glob as _glob, tempfile
import fxmeta

FIXINDEX_DIR = os.environ.get('FIXINDEX_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixes'))

# 去個案化：同主題（新舊 tgt⊆ts 或 overlap >= 門檻）即視為重複經驗
OVERLAP_THRESHOLD = 0.6


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
        norm = re.sub(r'[\s，。,.!?、:：;；()（）\[\]\{\}"\'`~\-—]+', '', text.lower())
        return {norm}


def _word_tokens(text):
    """Split into lowercase word tokens for domain matching (ignore short reads)."""
    return [t.lower() for t in re.split(r'[\s，。,.!?、:：;；()（）\[\]\{\}"\'`~\-—/]+', text)
            if len(t.strip()) >= 3]


def find_domain_file_auto(title, symps, etype='defect'):
    """Graded domain match for the no-arg `fi` pipeline (B1: refuse-to-guess).

    Candidate keywords = tokens drawn from the title + first symptom. A file
    matches ① when a candidate token == its slug exactly, or ② when one is a
    dash-prefix of the other. Only exact/prefix matches are used — substring
    matches are treated as ambiguous and a fresh file is created instead of
    polluting an existing one.
    """
    cand = list(dict.fromkeys(_word_tokens(title) + (_word_tokens(symps[0]) if symps else [])))
    if not cand:
        return None
    files = sorted(_glob.glob(os.path.join(FIXINDEX_DIR, '[0-9]*.md')))
    g1, g2 = {}, {}
    for fp in files:
        base = os.path.basename(fp)  # NNNN-slug.md
        if '-' not in base[:-3]:
            continue
        _id, slug = base[:-3].split('-', 1)
        try:
            with open(fp) as f:
                txt = f.read()
        except Exception:
            continue
        fm, _ = fxmeta.parse_frontmatter_full(txt)
        if str(fm.get('type') or 'defect') != etype:
            continue
        s = slug.lower()
        for t in set(cand):
            if t == s:
                g1[fp] = g1.get(fp, 0) + 1
            elif s.startswith(t + '-') or t.startswith(s + '-'):
                g2[fp] = g2.get(fp, 0) + 1
    # ①直接用：取命中 token 最多者（多檔平手時取最多，仍屬 ① 明確匹配）
    if g1:
        return max(g1, key=lambda k: g1[k])
    # ②直接用：僅當單一檔
    if len(g2) == 1:
        return next(iter(g2))
    return None


def _merge_symptoms(path, new_symps):
    """Append missing symptoms into the file's frontmatter symptoms: list."""
    with open(path) as f:
        lines = f.readlines()
    idx, existing = None, []
    for i, ln in enumerate(lines):
        m = re.match(r'^symptoms:[ \t]*(.*)$', ln)
        if m:
            idx = i
            val = m.group(1).strip()
            if val.startswith('[') and val.endswith(']'):
                inner = val[1:-1]
                existing = [x.strip().strip('"\'') for x in inner.split(',') if x.strip()]
            break
    if idx is None:
        return
    added = 0
    for s in new_symps:
        s = s.strip()
        if s and s not in existing:
            existing.append(s)
            added += 1
    if added == 0:
        return
    lines[idx] = 'symptoms: [' + ', '.join(existing) + ']\n'
    with open(path, 'w') as f:
        f.writelines(lines)


def _append_to_file(path, title, symps, root, fix, verify, detail=''):
    """Append a renumbered §N section to an existing file. NEVER rewrites its
    title (B2); snapshots the original to /tmp first (B3)."""
    import time, shutil
    with open(path) as f:
        txt = f.read()
    snap = os.path.join(tempfile.gettempdir(),
                        f'fi-undo-{os.path.basename(path)}.{os.getpid()}')
    try:
        shutil.copy(path, snap)
    except Exception:
        snap = None
    secs = [int(m) for m in re.findall(r'^## §(\d+)', txt, re.M)]
    n = (max(secs) + 1) if secs else 1
    lines = [f'## §{n} {title or "記錄"}', '']
    lines.append('**Symptom:** ' + '; '.join(symps))
    lines.append('')
    lines.append('**Root cause:** ' + root)
    lines.append('')
    lines.append('**Fix:** ' + fix)
    lines.append('')
    lines.append('**Verify:** ' + verify)
    lines.append('')
    if detail:
        lines.append(detail)
        lines.append('')
    with open(path, 'a') as f:
        f.write('\n' + '\n'.join(lines) + '\n')
    _merge_symptoms(path, symps)
    return snap, n



def find_duplicate(title, etype='defect'):
    """Return (fid, overlap_ratio) if an existing title contains ALL tokens of
    the new title (tgt ⊆ ts) or shares >= OVERLAP_THRESHOLD of the existing
    title's tokens (同主題含新語彙 → still supersede).

    Dedup 直覺（對齊 '不記個案'）：新經驗的關鍵詞若都已在某舊條目標題出現過
    （tgt ⊆ ts），或新標題涵蓋舊標題 >= OVERLAP_THRESHOLD 比例的關鍵詞，
    視為重複經驗, 回傳舊條目供 supersede 取代。
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
        # 同型過濾：insight 與 defect 不互相 supersede（預設 defect）
        if str(fm.get('type') or 'defect') != etype:
            continue
        t = fm.get('title') or os.path.basename(fp)
        ts = _title_tokens(str(t))
        if not ts:
            continue
        if tgt <= ts or (len(tgt & ts) / len(ts) >= OVERLAP_THRESHOLD):
            overlap = len(tgt & ts) / len(ts)   # 新詞涵蓋舊標題比例
            if best is None or overlap > best[1]:
                best = (os.path.basename(fp)[:4], round(overlap, 2))
    return best


def build_entry(fid, title, symptoms, root, fix, verify, slug, tags=None, detail=''):
    parts = []
    parts.append('---')
    parts.append(f'id: {fid}')
    parts.append(f'slug: {slug}')
    parts.append(f'title: {title}')
    tag_items = ['auto', 'shadow'] + (tags or [])
    parts.append('tags:\n' + '\n'.join(f'  - {t}' for t in tag_items))
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
    if detail:
        parts.append('')
        parts.append('## §5 詳情')
        parts.append('')
        parts.append(detail)
    return '\n'.join(parts) + '\n'


def _resolve_index_file():
    """FIXINDEX_INDEX 取值：環境早已由呼叫者 export 鎖定者，僅當它與
    FIXINDEX_DIR 同庫（dirname 相同）才沿用，否則一律改算到
    <FIXINDEX_DIR 的上層>/FIX-INDEX.md，防止 shell 全域殘留的 FIXINDEX_INDEX
    把 sandbox re-index 寫進真實庫。"""
    env_index = os.environ.get('FIXINDEX_INDEX')
    if env_index and os.path.dirname(os.path.abspath(env_index)) == os.path.dirname(os.path.abspath(FIXINDEX_DIR)):
        return env_index
    return os.path.join(os.path.dirname(FIXINDEX_DIR), 'FIX-INDEX.md')


def _run_index(cmd, *args):
    """Run a fixindex subcommand bound to THIS FIXINDEX_DIR and its index file
    (so sandbox tests don't leak into the real library). Uses the fixindex
    next to this file. list-arg subprocess（路徑帶空格不炸）。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixindex')
    if not os.path.exists(script):
        script = 'fixindex'  # fall back to PATH
    env = dict(os.environ)
    env['FIXINDEX_DIR'] = FIXINDEX_DIR
    env['FIXINDEX_INDEX'] = _resolve_index_file()
    quiet = not cmd.startswith('re-index')
    if cmd == 're-index':
        return subprocess.run([script] + cmd.split(' ') + list(args), env=env)
    if quiet:
        return subprocess.run([script] + cmd.split(' ') + list(args), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.run([script] + cmd.split(' ') + list(args), env=env)


def _git_commit_push(paths):
    """If FIXINDEX_DIR sits inside a git repo, add the given paths, commit with
    a fixindex message, and push. Returns a dict reflecting reality
    (宣告≠生效): committed=<short hash>|None, pushed=bool, git_error=<str>|None.
    All git calls use list-arg subprocess (no shell, no '>' redirect chars).
    Raises RuntimeError on commit/add failure (so caller can set exit code)."""
    try:
        r = subprocess.run(
            ['git', '-C', FIXINDEX_DIR, 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True)
    except Exception as e:
        return {'committed': None, 'pushed': False, 'git_error': f'git unavailable: {e}'}
    repo = (r.stdout or '').strip()
    if r.returncode != 0 or not repo:
        # 不在 git repo（sandbox）→ 不算錯誤
        return {'committed': None, 'pushed': False, 'git_error': None}

    # macOS /tmp → /private/tmp symlink：統一用 realpath 比對與算相對路徑
    fixdir_real = os.path.realpath(FIXINDEX_DIR)
    if not os.path.realpath(fixdir_real).startswith(os.path.realpath(repo) + os.sep):
        return {'committed': None, 'pushed': False, 'git_error': None}

    rel = []
    for p in paths:
        rp = os.path.realpath(p)
        if os.path.exists(rp):
            rel.append(os.path.relpath(rp, os.path.realpath(repo)))
    add = subprocess.run(['git', '-C', repo, 'add', '--'] + rel,
                         capture_output=True, text=True)
    if add.returncode != 0:
        return {'committed': None, 'pushed': False,
                'git_error': f'git add: {(add.stderr or add.stdout).strip()[:200]}'}
    # commit only if there are staged changes
    diff = subprocess.run(['git', '-C', repo, 'diff', '--cached', '--quiet'],
                          capture_output=True, text=True)
    if diff.returncode == 0:
        return {'committed': None, 'pushed': False, 'git_error': None}  # 無變動
    title = os.path.basename(paths[0]) if paths else 'update'
    cmsg = f"fixindex: {title}"
    cm = subprocess.run(['git', '-C', repo, 'commit', '-m', cmsg],
                        capture_output=True, text=True)
    if cm.returncode != 0:
        return {'committed': None, 'pushed': False,
                'git_error': f'git commit: {(cm.stderr or cm.stdout).strip()[:200]}'}
    short = 'unknown'
    m = re.search(r'\[[^\]]+ ([0-9a-f]{7,})', cm.stdout or '')
    if m:
        short = m.group(1)
    push = subprocess.run(['git', '-C', repo, 'push'],
                          capture_output=True, text=True)
    if push.returncode != 0:
        return {'committed': short, 'pushed': False,
                'git_error': f'git push: {(push.stderr or push.stdout).strip()[:200]}'}
    return {'committed': short, 'pushed': True, 'git_error': None}


def _pull_first_if_repo():
    """寫入前 pull-first：若 FIXINDEX_DIR 在 git repo，先收 remote 變更，避免在
    落後上游直接 commit+push（仿 0394 force-push 覆寫事故）。sandbox（非 git）
    為 no-op。失敗→回傳錯誤字串（呼叫端決定中止）。"""
    try:
        r = subprocess.run(
            ['git', '-C', FIXINDEX_DIR, 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True)
    except Exception:
        return None
    repo = (r.stdout or '').strip()
    if r.returncode != 0 or not repo:
        return None
    pf = subprocess.run(['git', '-C', repo, 'pull', '--rebase', '--autostash'],
                        capture_output=True, text=True)
    if pf.returncode != 0:
        return f'pull-first: {(pf.stderr or pf.stdout).strip()[:200]}'
    return None


def build_entry_insight(fid, title, context, insight, implication, revisit, slug,
                        queries, tags=None, detail=''):
    """Insight 條目 scaffold：frontmatter 帶 `type: insight`，symptoms=QUERIES（未來查詢句），
    body §1 Context / §2 Insight / §3 Implication / §4 Revisit-when。"""
    parts = []
    parts.append('---')
    parts.append(f'id: {fid}')
    parts.append(f'slug: {slug}')
    parts.append('type: insight')
    parts.append(f'title: {title}')
    tag_items = ['auto', 'insight'] + (tags or [])
    parts.append('tags:\n' + '\n'.join(f'  - {t}' for t in tag_items))
    parts.append('symptoms:')
    for q in queries:
        parts.append(f'  - {q}')
    parts.append('status: active')
    parts.append('supersedes: []')
    parts.append('related: []')
    parts.append('---')
    parts.append('')
    parts.append(f'# {fid} {title}')
    parts.append('')
    parts.append('## §1 Context')
    parts.append('')
    parts.append(context)
    parts.append('')
    parts.append('## §2 Insight')
    parts.append('')
    parts.append(insight)
    parts.append('')
    parts.append('## §3 Implication')
    parts.append('')
    parts.append(implication)
    parts.append('')
    parts.append('## §4 Revisit-when')
    parts.append('')
    parts.append(revisit)
    if detail:
        parts.append('')
        parts.append('## §5 詳情')
        parts.append('')
        parts.append(detail)
    return '\n'.join(parts) + '\n'


def _append_to_file_insight(path, title, context, insight, implication, revisit,
                            queries, detail=''):
    """Insight 版 domain append：§N 用 Context/Insight/Implication/Revisit-when 標籤，
    並把 QUERIES 併入 frontmatter symptoms（未來查詢句可被 find 命中）。"""
    import shutil
    with open(path) as f:
        txt = f.read()
    snap = os.path.join(tempfile.gettempdir(),
                        f'fi-undo-{os.path.basename(path)}.{os.getpid()}')
    try:
        shutil.copy(path, snap)
    except Exception:
        snap = None
    secs = [int(m) for m in re.findall(r'^## §(\d+)', txt, re.M)]
    n = (max(secs) + 1) if secs else 1
    lines = [f'## §{n} {title or "記錄"}', '']
    lines.append('**Context:** ' + context)
    lines.append('')
    lines.append('**Insight:** ' + insight)
    lines.append('')
    lines.append('**Implication:** ' + implication)
    lines.append('')
    lines.append('**Revisit-when:** ' + revisit)
    lines.append('')
    if detail:
        lines.append(detail)
        lines.append('')
    with open(path, 'a') as f:
        f.write('\n' + '\n'.join(lines) + '\n')
    _merge_symptoms(path, queries)
    return snap, n


def _pipeline_insight(ini, detail, mode, tags_arg):
    """INSIGHT: pipe 的寫入管線（shadow/dedup-supersede/domain-append/newfile，
    與 defect 管線平行；etype 全帶 insight）。QUERIES → symptoms 供未來查詢。"""
    title = (ini.get('insight') or ini.get('context') or 'untitled')[:80]
    if not title.strip():
        print('INSIGHT or CONTEXT required for insight mode (provide CONTEXT: / INSIGHT:)',
              file=sys.stderr)
        sys.exit(1)
    context = ini.get('context', '')
    insight = ini.get('insight', '')
    impl = ini.get('implication', '')
    revisit = ini.get('revisit-when', '')
    queries = [q.strip() for q in re.split(r'[,，]', ini.get('queries', '')) if q.strip()]
    if not queries:
        queries = [insight.strip()] if insight.strip() else []
    tags = []
    if tags_arg:
        tags = [t.strip() for t in re.split(r'[,，\s]+', tags_arg) if t.strip()]
    # matching symps 用 CONTEXT（對應 defect SYMPTOM 做 domain/dedup 分級）
    symps = [s.strip() for s in context.split(';') if s.strip()] or queries[:1]

    dup = find_duplicate(title, etype='insight')
    if mode == '--shadow':
        payload = {'etype': 'insight',
                   'preview_lines': len(build_entry_insight(
                       next_id(), title, context, insight, impl, revisit, '',
                       queries, tags).split('\n'))}
        payload['dedup'] = {'supersedes': dup[0], 'overlap': round(dup[1], 2)} if dup else None
        print(json.dumps(payload))
        return

    if dup:
        old_id = dup[0]
        new_id = next_id()
        slug = slugify(title)
        entry = build_entry_insight(new_id, title, context, insight, impl, revisit,
                                    slug, queries, tags, detail)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        import glob as _g
        old_files = sorted(_g.glob(os.path.join(FIXINDEX_DIR, f'{old_id}-*.md')))
        path = os.path.join(FIXINDEX_DIR, f'{new_id}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _run_index(f'supersede {old_id} {new_id}')
        payload = {'created': path, 'dedup': True, 'supersedes': old_id}
        payload.update(_git_commit_push([path, _resolve_index_file()] + old_files))
        print(json.dumps(payload))
        if payload.get('git_error'):
            sys.exit(1)
        return

    match = find_domain_file_auto(title, symps, etype='insight')
    if match:
        snap, secn = _append_to_file_insight(match, title, context, insight, impl,
                                             revisit, queries, detail)
        _run_index('re-index')
        payload = {'appended': os.path.basename(match), 'section': secn,
                   'dedup': False, 'undo': snap}
        payload.update(_git_commit_push([match, _resolve_index_file()]))
        print(json.dumps(payload))
        if payload.get('git_error'):
            sys.exit(1)
        return

    fid = next_id()
    slug = slugify(title)
    entry = build_entry_insight(fid, title, context, insight, impl, revisit,
                                slug, queries, tags, detail)
    os.makedirs(FIXINDEX_DIR, exist_ok=True)
    path = os.path.join(FIXINDEX_DIR, f'{fid}-{slug}.md')
    with open(path, 'w') as f:
        f.write(entry)
    _run_index('re-index')
    payload = {'created': path, 'dedup': False}
    payload.update(_git_commit_push([path, _resolve_index_file()]))
    print(json.dumps(payload))
    if payload.get('git_error'):
        sys.exit(1)
    return


def main():
    args = sys.argv[1:]
    plerr = _pull_first_if_repo()
    if plerr:
        print(json.dumps({'git_error': plerr, 'committed': None, 'pushed': False}))
        sys.exit(1)
    mode = None
    title_override = None
    symptom_arg = None
    fix_arg = None
    tags_arg = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--title' and i + 1 < len(args):
            title_override = args[i + 1]
            i += 1
        elif a == '--symptom' and i + 1 < len(args):
            symptom_arg = args[i + 1]
            i += 1
        elif a == '--fix' and i + 1 < len(args):
            fix_arg = args[i + 1]
            i += 1
        elif a == '--tags' and i + 1 < len(args):
            tags_arg = args[i + 1]
            i += 1
        elif a in ('--shadow', '--commit'):
            mode = a
        i += 1
    if not mode:
        print("usage: fxauto.py [--shadow|--commit] [--title T] [--symptom S] [--fix F] [--tags T]", file=sys.stderr)
        sys.exit(1)

    fields = {}
    # flags 是最高優先 baseline
    if symptom_arg:
        fields['symptom'] = symptom_arg
    if fix_arg:
        fields['fix'] = fix_arg
    # D2: stdin 一律讀（即使 flags 齊也不再靜默跳過）：
    #   - KEY 行（SYMPTOM/ROOT/FIX/VERIFY）補進 flags 沒給的欄位
    #   - 非 KEY 行整段保留 → §5 詳情（實測數據/無效嘗試落點）
    detail_lines = []
    insight_fields = {}
    stdin_text = sys.stdin.read() if not sys.stdin.isatty() else ''
    for raw in stdin_text.splitlines():
        st = raw.strip()
        m = re.match(r'^([A-Z][A-Z-]*):\s*(.+)', st)
        if m:
            k = m.group(1).lower()
            v = m.group(2).strip()
            if k in ('symptom', 'root', 'fix', 'verify'):
                fields.setdefault(k, v)
            elif k in ('context', 'insight', 'implication', 'revisit-when', 'queries', 'type'):
                insight_fields[k] = v
            else:
                detail_lines.append(raw)
        elif st:
            detail_lines.append(raw)
    detail = '\n'.join(detail_lines)

    # --- insight 路徑：INSIGHT: key 或 TYPE: insight → 改走 insight 管線，
    #     用 CONTEXT/INSIGHT/IMPLICATION/REVISIT-WHEN（對應 defect 的
    #     SYMPTOM/ROOT/FIX/VERIFY）+ QUERIES（未來查詢句 → symptoms）。
    #     etype 全帶 insight，與 defect 互不污染（insight/defect 不互相
    #     supersede、不互相 append）。---
    if ('insight' in insight_fields) or (insight_fields.get('type', '').strip().lower() == 'insight'):
        return _pipeline_insight(insight_fields, detail, mode, tags_arg)

    sympt = fields.get('symptom', '')
    if not sympt:
        # 自由文字容錯：無 SYMPTOM KEY 時，取首行非空、非 KEY 行當 symptom
        for raw in stdin_text.splitlines():
            st = raw.strip()
            if not st:
                continue
            if re.match(r'^[A-Z]+\s*:\s*\S', st) and st.split(':', 1)[0].lower() in ('symptom', 'root', 'fix', 'verify'):
                continue
            fields.setdefault('symptom', st)
            break
        sympt = fields.get('symptom', '')
    root = fields.get('root', 'untraced')
    fix = fields.get('fix', 'applied')
    verify = fields.get('verify', 'verified')

    if not sympt:
        print(
            "SYMPTOM required — stdin expects KEY: value lines. Minimal example:\n"
            "  echo 'SYMPTOM: web PUT /soul crashes on NUL path\n"
            "ROOT: os.open raises ValueError, only OSError caught\n"
            "FIX: catch (OSError, ValueError)\n"
            "VERIFY: pytest tests/x.py -q -> N passed' | fixindex auto --tags a,b\n"
            "(or pass --symptom/--fix/--tags flags without stdin)",
            file=sys.stderr,
        )
        sys.exit(1)

    symps = [s.strip() for s in sympt.split(';') if s.strip()]
    if not symps:
        symps = [sympt.strip()]

    # tags：--tags 透傳（逗號/空白分隔），或留 default auto/shadow
    if tags_arg:
        tags = [t.strip() for t in re.split(r'[,，\s]+', tags_arg) if t.strip()]
    else:
        tags = []

    title = (title_override or symps[0])[:80]
    dup = find_duplicate(title)

    if mode == '--shadow':
        payload = {'preview_lines': len(build_entry(next_id(), title, symps, root, fix, verify, '', tags).split('\n'))}
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
        slug = slugify(title)
        entry = build_entry(new_id, title, symps, root, fix, verify, slug, tags, detail)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        old_path = os.path.join(FIXINDEX_DIR, f'{old_id}-*.md')
        import glob as _g
        old_files = sorted(_g.glob(old_path))
        path = os.path.join(FIXINDEX_DIR, f'{new_id}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _run_index(f'supersede {old_id} {new_id}')
        payload = {'created': path, 'dedup': True, 'supersedes': old_id}
        git_paths = [path, _resolve_index_file()] + old_files
        payload.update(_git_commit_push(git_paths))
        print(json.dumps(payload))
        if payload.get('git_error'):
            sys.exit(1)
        return
    else:
        # 無重複 → 先試 domain append（分級匹配，拒猜；不中才建新檔）
        match = find_domain_file_auto(title, symps)
        if match:
            snap, secn = _append_to_file(match, title, symps, root, fix, verify, detail)
            _run_index('re-index')
            payload = {'appended': os.path.basename(match), 'section': secn,
                       'dedup': False, 'undo': snap}
            payload.update(_git_commit_push([match, _resolve_index_file()]))
            print(json.dumps(payload))
            if payload.get('git_error'):
                sys.exit(1)
            return
        fid = next_id()
        slug = slugify(title)
        entry = build_entry(fid, title, symps, root, fix, verify, slug, tags, detail)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        path = os.path.join(FIXINDEX_DIR, f'{fid}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _run_index('re-index')
        payload = {'created': path, 'dedup': False}
        payload.update(_git_commit_push([path, _resolve_index_file()]))
        print(json.dumps(payload))
        if payload.get('git_error'):
            sys.exit(1)
        return


if __name__ == '__main__':
    main()