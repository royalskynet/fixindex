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

import sys, os, json, re, subprocess, glob as _glob, tempfile, datetime
import fxmeta
import fxsync

# B2: STRICT_DIR=1 且未顯式設定 → 禁止回退（module 載入即擋，不給任何執行路徑）
if fxsync.strict_dir_guard(os.environ.get('FIXINDEX_DIR')):
    sys.stderr.write("fixindex: STRICT_DIR: FIXINDEX_DIR 未顯式設定，拒絕回退\n")
    sys.exit(1)

FIXINDEX_DIR = os.environ.get('FIXINDEX_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixes'))

# 去個案化：同主題（新舊 tgt⊆ts 或 overlap >= 門檻）即視為重複經驗
OVERLAP_THRESHOLD = 0.6


def _q(s):
    """統一 YAML quoting：一律經 fxmeta 的 quote/needs_quote，不手拼引號。

    防 YAML 特殊字元（`: `、`#`、`,`、引號、反斜線）破壞 frontmatter 純量欄位與
    block list item（0454/0458 教訓：三套寫檔實作格式互打、無跳脫 → 壞檔）。"""
    s = str(s)
    return fxmeta._yaml_quote(s) if fxmeta._needs_yaml_quotes(s) else s


def _intake_gate(rule):
    """INTAKE：建新條目前強制回答『未來的我知道了會不會表現不同』。
    只擋建新檔；append/supersede 不擋（個案本來就該當證據掛在既有條目下）。
    逃生門：FIXINDEX_NO_GATE=1。"""
    if os.environ.get('FIXINDEX_NO_GATE') == '1':
        return
    if rule and rule.strip():
        return
    print(
        "fixindex: INTAKE gate — 建新條目需要 RULE:（可泛化規則）\n"
        "  1. 拿掉本案的專案名／路徑／具體值，這條經驗還成立嗎？\n"
        "  2. 能不能提成「遇到這類問題先查什麼」的規則？\n"
        "  3. 真的只在個案有意義 → 不要建新條目，append 到既有條目當證據。\n"
        "\n"
        "  範例：\n"
        "    SYMPTOM: ...\n"
        "    ROOT: ...\n"
        "    FIX: ...\n"
        "    RULE: 佔位 key 填進 .env 比不填更糟——先清空佔位再排查 401\n"
        "\n"
        "  逃生門：FIXINDEX_NO_GATE=1",
        file=sys.stderr)
    sys.exit(1)


def next_id():
    files = sorted(_glob.glob(os.path.join(FIXINDEX_DIR, '[0-9]*.md')))
    if not files:
        return '0001'
    last = os.path.basename(files[-1])[:4]
    return f'{int(last) + 1:04d}'


# LINKER：BM25 find_related。「被判定為已知」→ append 當證據，不開新檔。
# 用 top/次高 raw-score ÷ ratio；見 find_related docstring 為何不能用絕對閾。
LINK_RATIO = float(os.environ.get('FIXINDEX_LINK_RATIO', '1.5'))


def _path_for_id(fid):
    """依條目 id 回傳 fixes/NNNN-*.md 完整路徑（唯一 4 碼前綴）。找不到回傳 None。"""
    files = sorted(_glob.glob(os.path.join(FIXINDEX_DIR, f'{fid}-*.md')))
    return files[0] if files else None


def find_related(query, etype='defect'):
    """LINKER：用純 BM25（raw score）找最相關既有條目。

    回傳 (fid, ratio) 或 None。判準是「top hit 對次高 hit 的領先比值」而非絕對
    分數——fxsearch CLI 把 top 正規化到 0..1，任何查詢頂部都是 1.0，絕對閾會把
    孤立詞/不相關查詢也收進去。真正重複的 raw BM25 會遠超次高（實測重複≈2.0+，
    新主題/孤立≈1.0-1.3）。命中且 ratio >= LINK_RATIO → 由呼叫端 append 當
    證據。檢索掛掉 → 回 None（不拒寫）。"""
    if not query or not query.strip():
        return None
    try:
        import fxsearch as X
        entries = X.build_entries(FIXINDEX_DIR)
        if etype:
            entries = [e for e in entries if e['type'] == etype]
        if not entries:
            return None
        raw = X.BM25Engine(entries).search(query, limit=5)
        if len(raw) < 2:
            return None
        top_i, top_s = raw[0]
        second_s = raw[1][1]
        ratio = (top_s / second_s) if second_s > 0 else 999.0
    except Exception:
        return None
    if ratio < LINK_RATIO:
        return None
    e = entries[top_i]
    return (e['file'][:4], round(ratio, 2))


def slugify(text, fallback='untitled'):
    import unicodedata
    s = unicodedata.normalize('NFKD', text.lower())
    out = re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60]
    if not out:
        # 全中文/全符號 title 會塌成空字串 → 檔名變 NNNN-.md，索引與檔名都認不出內容。
        # bash 端 slugify() 對此直接 die；python 端走 fi 管線不能中斷寫入（內容已備妥），
        # 因此退回 fallback，並在 stderr 留痕讓呼叫者知道 slug 沒有語意。
        print(f'fixindex: slug normalized to empty, falling back to {fallback!r} (got: {text!r})',
              file=sys.stderr)
        return fallback
    return out


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


def _derive_title(text, limit=60):
    """從首個 symptom 推標題：先找句號類終止符（。．.！？ 是最理想切點），
    找不到才退回次級斷句符（；;，,、（(【—）；兩輪都無邊界才退回硬切，
    並一律補 `…`（讓截斷肉眼可辨，也給 doctor 正向指紋）。"""
    text = str(text).strip()
    if not text:
        return 'untitled'
    if len(text) <= limit:
        return text
    # 句號類是最理想的切點，必須優先；次級（頓號/逗號/括號/破折號）才是退路。
    # 原本只有次級集合，導致標題切在句中而非句末。
    cuts_strong = '。．.！!？?'
    cuts_weak = '；;，,、（(【—'
    # 第一輪：句號類，從後往前找 ≤limit 的最長切點
    best = -1
    for i in range(limit - 1, -1, -1):
        if text[i] in cuts_strong:
            best = i
            break
    # 第二輪：次級斷句符（僅當第一輪沒找到）
    if best < 0:
        for i in range(limit - 1, -1, -1):
            if text[i] in cuts_weak:
                best = i
                break
    if best >= 0:
        return text[:best + 1].rstrip('；;，,、（(【—-–—。．.！!？? ')
    # 無邊界 → 硬切補 …
    return text[:limit] + '…'


def _merge_symptoms(path, new_symps):
    """Append missing symptoms into the file's frontmatter symptoms: list.

    整段置換（非改首行）：只在 frontmatter 區間內操作，吞 flow + block 兩型既有
    項目（hybrid 壞檔正是兩型並存），合併新症狀後以 block list 重寫。flow 內文用
    yaml.safe_load 切分，不用裸 `,`（避免 0001 那種一句被逗號切兩筆的斷句錯誤，
    0454 教訓）。找不到 symptoms: 就 return 不回滾（body 已先 append）。
    """
    import yaml as _yaml
    with open(path) as f:
        lines = f.readlines()
    # 找 frontmatter 邊界：第一個 --- 到第二個 ---，只在區間內操作
    starts = [i for i, ln in enumerate(lines) if ln.strip() == '---']
    if len(starts) < 2:
        return
    a, b = starts[0], starts[1]
    # 找 symptoms: 起始行
    start = None
    for i in range(a + 1, b):
        if re.match(r'^symptoms:', lines[i]):
            start = i
            break
    if start is None:
        return
    headval = lines[start].split(':', 1)[1].strip()
    existing = []
    # flow 內容：先用 yaml 切（退化才用逗號）
    if headval.startswith('[') and headval.endswith(']'):
        inner = headval[1:-1]
        if inner.strip():
            try:
                existing = [str(x).strip() for x in _yaml.safe_load('[' + inner + ']')]
            except Exception:
                existing = [x.strip().strip('"\'') for x in inner.split(',') if x.strip()]
    # block items 一律從 symptoms: 下一行開始掃（純 block 或 hybrid 都吃得到）
    idx = start + 1
    while idx < b:
        li = re.match(r'^\s*-\s+(.*)$', lines[idx])
        if not li:
            break
        existing.append(li.group(1).strip().strip('"\''))
        idx += 1
    end = idx
    # 去重保序（比對 strip 後值）
    seen = {}
    merged = []
    for v in list(existing) + [s.strip() for s in new_symps]:
        k = v.strip()
        if k and k not in seen:
            seen[k] = True
            merged.append(v)
    # 整段置換為 block list（一律 block，格式定於一尊）
    lines[start:end] = ['symptoms:\n'] + [f'  - {_q(s)}\n' for s in merged]
    with open(path, 'w') as f:
        f.writelines(lines)


def _append_to_file(path, title, symps, root, fix, verify, detail='', trust=None):
    """Append a renumbered §N section to an existing file. NEVER rewrites its
    title (B2); snapshots the original to /tmp first (B3). trust: dict like
    {'evidence': '...'} → writes **State:** verified / **Evidence:** /
    **Last verified:** (today) into the new section (legacy otherwise)."""
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
    if trust and trust.get('evidence'):
        lines.append('**State:** verified')
        lines.append(f"**Evidence:** {trust['evidence']}")
        lines.append(f'**Last verified:** {datetime.date.today().isoformat()}')
        lines.append('')
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
    _verify_written(path, snap=snap)   # 2d: append 後立即驗合併後 frontmatter，壞則還原快照
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


def build_entry(fid, title, symptoms, root, fix, verify, slug, tags=None, detail='',
                evidence=None, rule=''):
    """Build a defect entry scaffold. If evidence is non-empty AND verify is
    non-empty, the first section is marked **State:** verified with **Evidence:**
    and **Last verified:** (today, ISO). Otherwise legacy-compatible (no trust
    fields). rule (RULE:) is written into the body so fxsearch/grep can reach it."""
    parts = []
    parts.append('---')
    parts.append(f'id: "{fid}"')
    parts.append(f'slug: {_q(slug)}')
    parts.append(f'title: {_q(title)}')
    tag_items = list(tags or [])
    if tag_items:
        parts.append('tags:\n' + '\n'.join(f'  - {_q(t)}' for t in tag_items))
    parts.append('symptoms:')
    for s in symptoms:
        parts.append(f'  - {_q(s)}')
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
    if evidence and str(verify or '').strip():
        today = datetime.date.today().isoformat()
        parts.append('')
        parts.append('**State:** verified')
        parts.append(f'**Evidence:** {evidence}')
        parts.append(f'**Last verified:** {today}')
    if rule and rule.strip():
        parts.append('')
        parts.append(f'**Rule:** {rule.strip()}')
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
    # Windows 相容：`fixindex` 是 `#!/usr/bin/env bash` 腳本，native Windows Python
    # 的 subprocess CreateProcess 無法直接執行無副檔名的 shell 腳本
    # → OSError: [WinError 193]（不是有效的 Win32 應用程式），中斷 fi 的 re-index 收尾。
    # 用 `bash <script>` 包裝（呼應 .bin/python3 shim 策略）；POSIX 維持原樣直跑。
    launch = ['bash', script] if os.name == 'nt' else [script]
    env = fxsync.child_env(dict(os.environ))
    env['FIXINDEX_DIR'] = FIXINDEX_DIR
    env['FIXINDEX_INDEX'] = _resolve_index_file()
    # bash 子指令（re-index/supersede）只產檔/重建 index，不自己 commit+push；
    # commit/push 統一由 fxauto 結尾單一 _git_commit_push 收（paths 已含 index/old/new）
    # → 修 0171 復發（fxauto 每回合 2 commits：子指令 push + 結尾 push）
    env['FIXINDEX_NO_SYNC'] = '1'
    quiet = not cmd.startswith('re-index')
    if cmd == 're-index':
        return subprocess.run(launch + cmd.split(' ') + list(args), env=env)
    if quiet:
        return subprocess.run(launch + cmd.split(' ') + list(args), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.run(launch + cmd.split(' ') + list(args), env=env)


def _verify_written(path, snap=None):
    """寫完立刻驗 frontmatter；壞了就還原（append）或刪除（新檔）並非零退出。

    硬規則：驗失敗一律在 _run_index / _git_commit_push 之前退出，壞資料不進 index、
    不進 git（「宣告 ≠ 生效」：不能寫完就宣稱成功，要重讀磁碟驗證）。"""
    import shutil as _sh, sys as _sys
    try:
        txt = open(path, encoding='utf-8').read()
        fm, _ = fxmeta.parse_frontmatter_full(txt)
        head = txt.split('---\n')[1]
        yaml_lib = __import__('yaml')
        yaml_lib.safe_load(head)
        if not fm or not str(fm.get('id') or '').strip():
            raise ValueError('frontmatter missing id')
    except Exception as e:
        if snap and os.path.exists(snap):
            try:
                _sh.copy(snap, path)      # append 路徑：還原快照
            except Exception:
                pass
        elif os.path.exists(path):
            try:
                os.remove(path)           # 新檔路徑：直接刪
            except Exception:
                pass
        print(json.dumps({'error': 'frontmatter_verify_failed',
                          'file': path, 'detail': str(e)}))
        _sys.exit(1)


def _compress():
    """COMPRESSOR：新寫入的 § 壓成一行 blurb 進 .blurbs.jsonl（fxsearch 用）。
    LLM 在本機 OmniRoute，離線是常態 → 失敗一律吞掉，絕不阻斷寫入。
    逃生門：FIXINDEX_NO_BLURB=1。"""
    if os.environ.get('FIXINDEX_NO_BLURB') == '1':
        return
    blurb = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fxblurb.py')
    try:
        subprocess.run(['python3', blurb, '--limit=5'],
                       env={**os.environ, 'FIXINDEX_DIR': FIXINDEX_DIR,
                            'FIXINDEX_NO_BLURB': '1'},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=45)
    except Exception:
        pass   # ponytail: 壓縮是加分項，不是寫入前提


def _git_commit_push(paths):
    """Thin wrapper over fxsync.push — 維持 fxauto 既有 JSON 契約。

    committed=<short hash>|None, pushed=bool, git_error=<str>|None。
    git_error 只在 kind ∈ (conflict, fatal) 填（離線不 die：另給 pending_push=True，
    caller 的 git_error 檢查因此不 exit 1）。所有 git 由 fxsync 統一執行。"""
    res = fxsync.push(FIXINDEX_DIR, paths=paths)
    out = {'committed': res.get('committed'), 'pushed': bool(res.get('pushed')),
           'git_error': None}
    if res.get('kind') in ('conflict', 'fatal'):
        out['git_error'] = res.get('detail') or res.get('reason') or 'sync_push 失敗'
    if res.get('kind') == 'offline':
        out['pending_push'] = True
    return out


def _pull_first_if_repo():
    """寫入前 pull-first（fxsync.pull）。sandbox（非 git）→ no-op；離線 → 續跑
    （push 端會留 pending marker）。失敗→回傳錯誤字串（呼叫端中止）。"""
    res = fxsync.pull(FIXINDEX_DIR)
    if not res.get('ok'):
        return res.get('reason') or res.get('stderr') or 'pull-first 失敗'
    return None


def build_entry_insight(fid, title, context, insight, implication, revisit, slug,
                        queries, tags=None, detail='', rule=''):
    """Insight 條目 scaffold：frontmatter 帶 `type: insight`，symptoms=QUERIES（未來查詢句），
    body §1 Context / §2 Insight / §3 Implication / §4 Revisit-when。rule (RULE:)
    寫進 body 供 grep / fxsearch 檢索。"""
    parts = []
    parts.append('---')
    parts.append(f'id: "{fid}"')
    parts.append(f'slug: {_q(slug)}')
    parts.append('type: insight')
    parts.append(f'title: {_q(title)}')
    tag_items = ['insight'] + list(tags or [])
    if tag_items:
        parts.append('tags:\n' + '\n'.join(f'  - {_q(t)}' for t in tag_items))
    parts.append('symptoms:')
    for q in queries:
        parts.append(f'  - {_q(q)}')
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
    if rule and rule.strip():
        parts.append('')
        parts.append(f'**Rule:** {rule.strip()}')
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
    _verify_written(path, snap=snap)   # 2d: append 後立即驗，壞則還原快照
    return snap, n


# §6: repeat → eval 提示。只在寫入路徑（fi/auto committed）觸發；最多一則。
def repeat_eval_hint(path, title, symps, new_secn=None):
    """Return a hint line
    FIXINDEX_REPEAT_EVAL key=<ID#N> reason=<repeat|failed_outcome> recommendation=...
    or None. Triggers (once):
      - repeat: same domain file already has >=3 sections whose heading tokens
        overlap the incoming title/symptoms >= 50%.
      - failed_outcome: the section being written already has Outcome failed>=2.
    Never mutates; never spawns; at most one line."""
    if not title:
        return None
    base = os.path.basename(path)
    try:
        with open(path, encoding='utf-8') as f:
            txt = f.read()
    except Exception:
        return None
    try:
        import fxsearch
        inc = set(fxsearch.tokenize(title))
        for s in symps:
            inc |= set(fxsearch.tokenize(s))
    except Exception:
        inc = set()
    _, body_start = fxmeta.parse_frontmatter_full(txt)
    similar = 0
    first_reason = None
    for num, heading, body in fxmeta.iter_sections(txt, body_start):
        # repeat: count highly-similar headings
        hs = set()
        try:
            hs = set(fxsearch.tokenize(heading))
        except Exception:
            hs = set()
        if hs and inc and (len(inc & hs) / max(len(hs), 1)) >= 0.5:
            similar += 1
            if similar >= 3 and not first_reason:
                first_reason = f'FIXINDEX_REPEAT_EVAL key={base[:4]}#{num} reason=repeat recommendation=regression_test'
        # failed_outcome: target section (or any section when appending new)
        if not first_reason and (new_secn is None or num == new_secn):
            _, _, outcome, _ = fxmeta.section_summary(body)
            if outcome.get('failed', 0) >= 2:
                first_reason = f'FIXINDEX_REPEAT_EVAL key={base[:4]}#{num} reason=failed_outcome recommendation=health_check'
    return first_reason


def _pipeline_insight(ini, detail, mode, tags_arg, defer_commit=False):
    """INSIGHT: pipe 的寫入管線（shadow / dedup-supersede / domain-append / new-file，
    與 defect 管線平行；etype 全帶 insight）。QUERIES → symptoms 供未來查詢。

    回傳 (payload, touched_paths)。defer_commit=False 時各分支結尾自行
    payload.update(_git_commit_push(paths))——單一 commit，行為與 inline 版位元一致。
    """
    title = _derive_title(ini.get('insight') or ini.get('context') or 'untitled')
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
    # matching symps 用 CONTEXT（對應 defect 的 SYMPTOM 做 domain/dedup 分級）
    symps = [s.strip() for s in context.split(';') if s.strip()] or queries[:1]

    dup = find_duplicate(title, etype='insight')
    if mode == '--shadow':
        payload = {'etype': 'insight',
                   'preview_lines': len(build_entry_insight(
                       next_id(), title, context, insight, impl, revisit, '',
                       queries, tags).split('\n'))}
        payload['dedup'] = {'supersedes': dup[0], 'overlap': round(dup[1], 2)} if dup else None
        return payload, []

    if dup:
        old_id = dup[0]
        new_id = next_id()
        slug = slugify(title, fallback='insight')
        entry = build_entry_insight(new_id, title, context, insight, impl, revisit,
                                    slug, queries, tags, detail)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        import glob as _g
        old_files = sorted(_g.glob(os.path.join(FIXINDEX_DIR, f'{old_id}-*.md')))
        path = os.path.join(FIXINDEX_DIR, f'{new_id}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _verify_written(path)   # 2d: 寫完即驗，壞檔不進 index/git
        _run_index(f'supersede {old_id} {new_id}')
        payload = {'etype': 'insight', 'created': path, 'dedup': True, 'supersedes': old_id}
        paths = [path, _resolve_index_file()] + old_files
        if not defer_commit:
            payload.update(_git_commit_push(paths))
        return payload, paths

    match = find_domain_file_auto(title, symps, etype='insight')
    if match:
        snap, secn = _append_to_file_insight(match, title, context, insight, impl,
                                             revisit, queries, detail)
        _run_index('re-index')
        payload = {'etype': 'insight', 'appended': os.path.basename(match), 'section': secn,
                   'dedup': False, 'undo': snap}
        paths = [match, _resolve_index_file()]
        if not defer_commit:
            payload.update(_git_commit_push(paths))
        return payload, paths

    # LINKER：BM25 找最相關 insight 條目 → append，不開新檔。
    rel = find_related(title, 'insight')
    if rel:
        ref_id, ref_score = rel
        ref_path = _path_for_id(ref_id)
        if ref_path:
            snap, secn = _append_to_file_insight(ref_path, title, context, insight,
                                                 impl, revisit, queries, detail)
            _run_index('re-index')
            payload = {'etype': 'insight', 'linked': ref_id, 'score': round(ref_score, 3),
                       'appended': os.path.basename(ref_path), 'section': secn,
                       'dedup': False, 'undo': snap}
            paths = [ref_path, _resolve_index_file()]
            if not defer_commit:
                payload.update(_git_commit_push(paths))
            return payload, paths

    # INTAKE gate：LINKER 未收容、要開新 insight 條目時才強制回答可泛化。
    _intake_gate(ini.get('rule', ''))
    fid = next_id()
    slug = slugify(title, fallback='insight')
    entry = build_entry_insight(fid, title, context, insight, impl, revisit,
                                slug, queries, tags, detail, rule=ini.get('rule', ''))
    os.makedirs(FIXINDEX_DIR, exist_ok=True)
    path = os.path.join(FIXINDEX_DIR, f'{fid}-{slug}.md')
    with open(path, 'w') as f:
        f.write(entry)
    _verify_written(path)   # 2d: 寫完即驗
    _run_index('re-index')
    payload = {'etype': 'insight', 'created': path, 'dedup': False}
    paths = [path, _resolve_index_file()]
    if not defer_commit:
        payload.update(_git_commit_push(paths))
    return payload, paths

def _pipeline_defect(fields, detail, mode, tags_arg, title_override, defer_commit=False):
    """Defect 寫入管線（shadow / dedup-supersede / domain-append / new-file），
    抽自 main() 688-745 行。不含首行容錯推斷與 SYMPTOM required 報錯（留在 main）。

    回傳 (payload, touched_paths)。defer_commit=False 時結尾自行
    payload.update(_git_commit_push(paths))——單一 commit，行為與 inline 版位元一致。
    """
    sympt = fields.get('symptom', '')
    root = fields.get('root', 'untraced')
    fix = fields.get('fix', 'applied')
    verify = fields.get('verify', 'verified')
    evidence = fields.get('evidence', '')

    symps = [s.strip() for s in sympt.split(';') if s.strip()]
    if not symps:
        symps = [sympt.strip()]

    if tags_arg:
        tags = [t.strip() for t in re.split(r'[,，\s]+', tags_arg) if t.strip()]
    else:
        tags = []

    # title_override 存在（呼叫端已明示意圖）→ 原樣採用不截斷；否則從首個
    # symptom 走 _derive_title（子句邊界切、找不到補 …，不再硬切 80）
    title = title_override if title_override else _derive_title(symps[0] if symps else 'untitled')
    dup = find_duplicate(title)

    if mode == '--shadow':
        payload = {'preview_lines': len(build_entry(next_id(), title, symps, root, fix, verify, '', tags, '', evidence).split('\n'))}
        if dup:
            payload['dedup'] = {'supersedes': dup[0], 'overlap': round(dup[1], 2)}
        else:
            payload['dedup'] = None
        return payload, []

    if dup:
        # 去個案化：取代舊條目, 不創重複檔
        old_id = dup[0]
        new_id = next_id()
        slug = slugify(title)
        entry = build_entry(new_id, title, symps, root, fix, verify, slug, tags, detail, evidence)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        old_path = os.path.join(FIXINDEX_DIR, f'{old_id}-*.md')
        import glob as _g
        old_files = sorted(_g.glob(old_path))
        path = os.path.join(FIXINDEX_DIR, f'{new_id}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _verify_written(path)   # 2d: 寫完即驗，壞檔不進 index/git
        _run_index(f'supersede {old_id} {new_id}')
        payload = {'created': path, 'dedup': True, 'supersedes': old_id}
        paths = [path, _resolve_index_file()] + old_files
        # §6: dedup-supersede 也算「同一 domain 反覆相似故障」——若被取代檔
        # 已有 >=3 相似 section，仍提示（同次最多一則）。
        hint_path = old_files[0] if old_files else path
        hint = repeat_eval_hint(hint_path, title, symps, new_secn=None)
        if hint:
            print(hint, file=sys.stderr)
        if not defer_commit:
            payload.update(_git_commit_push(paths))
        return payload, paths
    else:
        # 無重複 → 先試 domain append（分級匹配，拒猜；不中才建新檔）
        match = find_domain_file_auto(title, symps)
        if match:
            entry_meta = {'evidence': evidence} if (evidence and verify.strip()) else {}
            snap, sec = _append_to_file(match, title, symps, root, fix, verify, detail,
                                        trust=entry_meta)
            _run_index('re-index')
            payload = {'appended': os.path.basename(match), 'section': sec,
                       'dedup': False, 'undo': snap}
            paths = [match, _resolve_index_file()]
            hint = repeat_eval_hint(match, title, symps, new_secn=sec)
            if hint:
                print(hint, file=sys.stderr)
            if not defer_commit:
                payload.update(_git_commit_push(paths))
            return payload, paths
        # LINKER：BM25 找最相關既有條目。「被判定為已知」→ append 當證據，不開新檔。
        rel = find_related(title, 'defect')
        if rel:
            ref_id, ref_score = rel
            ref_path = _path_for_id(ref_id)
            if ref_path:
                entry_meta = {'evidence': evidence} if (evidence and verify.strip()) else {}
                snap, sec = _append_to_file(ref_path, title, symps, root, fix, verify,
                                            detail, trust=entry_meta)
                _run_index('re-index')
                payload = {'linked': ref_id, 'score': round(ref_score, 3),
                           'appended': os.path.basename(ref_path), 'section': sec,
                           'dedup': False, 'undo': snap}
                paths = [ref_path, _resolve_index_file()]
                if not defer_commit:
                    payload.update(_git_commit_push(paths))
                return payload, paths
        # INTAKE gate：LINKER 未收容、真正要開新條目前才強制回答可泛化。
        _intake_gate(fields.get('rule', ''))
        fid = next_id()
        slug = slugify(title)
        entry = build_entry(fid, title, symps, root, fix, verify, slug, tags, detail,
                            evidence, rule=fields.get('rule', ''))
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        path = os.path.join(FIXINDEX_DIR, f'{fid}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _verify_written(path)   # 2d: 寫完即驗
        _run_index('re-index')
        payload = {'created': path, 'dedup': False}
        paths = [path, _resolve_index_file()]
        hint = repeat_eval_hint(path, title, symps, new_secn=1)
        if hint:
            print(hint, file=sys.stderr)
        if not defer_commit:
            payload.update(_git_commit_push(paths))
        return payload, paths


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
            if k in ('symptom', 'root', 'fix', 'verify', 'evidence'):
                fields.setdefault(k, v)
            elif k in ('context', 'insight', 'implication', 'revisit-when', 'queries', 'type'):
                insight_fields[k] = v
            elif k == 'rule':
                # RULE: 泛化規則 — defect 與 insight 共用
                fields['rule'] = v
                insight_fields['rule'] = v
            else:
                detail_lines.append(raw)
        elif re.match(r'^[A-Z][A-Z-]*:\s*$', st):
            # 裸 KEY 標籤、無值（如空模板 `SYMPTOM:`/`ROOT:`/`FIX:`/`VERIFY:`）——
            # 不是內容，省略。否則會被掉進 detail_lines 進而誤當 symptom，
            # append 成垃圾 §N 污染既有 entry（0437 被連續污染的根因）。
            continue
        elif st:
            detail_lines.append(raw)
    detail = '\n'.join(detail_lines)

    # --- 三態分流：判定 mixed / insight-only / defect-only ---
    has_insight_key = ('insight' in insight_fields) or (insight_fields.get('type', '').strip().lower() == 'insight')
    has_explicit_symptom = 'symptom' in fields

    if has_insight_key and has_explicit_symptom:
        # 混拆：defect 先寫、insight 後寫、頂層單 commit/push（無名 namespace 併同克哈希）。
        d_payload, d_paths = _pipeline_defect(fields, detail, mode, tags_arg, title_override, defer_commit=True)
        i_payload, i_paths = _pipeline_insight(insight_fields, '', mode, tags_arg, defer_commit=True)
        out = {'mixed': True, 'defect': d_payload, 'insight': i_payload}
        if mode == '--commit':
            all_paths = list(dict.fromkeys(d_paths + i_paths))
            out.update(_git_commit_push(all_paths))
        print(json.dumps(out, ensure_ascii=False))
        if out.get('git_error'):
            sys.exit(1)
        return
    elif has_insight_key:
        payload, _ = _pipeline_insight(insight_fields, detail, mode, tags_arg)
        print(json.dumps(payload, ensure_ascii=False))
        if payload.get('git_error'):
            sys.exit(1)
        return

    # --- 純 defect：先做首行容錯，SYMPTOM 必填 ---
    sympt = fields.get('symptom', '')
    if not sympt:
        # 自由文字容錯：無 SYMPTOM KEY 時，取首行非空、非 KEY 行當 symptom
        for raw in stdin_text.splitlines():
            st = raw.strip()
            if not st:
                continue
            if re.match(r'^[A-Z]+\s*:', st) and st.split(':', 1)[0].lower() in ('symptom', 'root', 'fix', 'verify'):
                continue
            fields.setdefault('symptom', st)
            break
        sympt = fields.get('symptom', '')

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

    payload, _ = _pipeline_defect(fields, detail, mode, tags_arg, title_override)
    print(json.dumps(payload, ensure_ascii=False))
    if payload.get('git_error'):
        sys.exit(1)
    return


if __name__ == '__main__':
    main()