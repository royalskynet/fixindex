#!/usr/bin/env python3
"""fxsearch.py — BM25 retrieval over fixindex entries with section-level indexing."""
import sys, os, json, re, math, collections, glob

# ── tokenizer ──
# 字典優先的 CJK 分詞（借鏡 claude-mem-lite）:
#   1. 字典詞組整 token（資料庫 → 資料庫）
#   2. 未命中部分 fallback 成疊字 bigram（修復 → 修/修复? 修復）
# 避免逐字 token 導致中文跨字詞召回破碎。
_CJK = r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff]'
# 精簡字典：fixindex 常見中文詞彙（可擴充）
CJK_COMPOUNDS = [
    '資料庫','數據庫','資料','數據','接口','函數','函式','變量','變數','元件','組件','模組','模塊',
    '配置','框架','部署','測試','調試','除錯','編譯','緩存','快取','索引','權限','權限','認證','授權',
    '加密','解密','併發','並發','異步','異步','執行緒','執行緒','進程','憑證','網關','監控','日誌','登錄',
    '前端','後端','程式碼','代碼','檔案','文件','專案','項目','修復','修補','重構','優化','升級','降級',
    '報錯','崩潰','超時','逾時','中斷','異常','隔離','發佈','發布','上線','回滾','回退','回退','遷移',
    '記憶體','內存','磁碟','磁盤','存儲','儲存','查詢','搜尋','检索','召回','診斷','症狀','根因','驗證',
    '運行','執行','啟動','重啟','停止','關閉','開啟','透過','啟用','停用','預設','默認','環境','依賴',
    '錯誤','失敗','成功','警告','告警','登入','登出','帳號','密碼','金鑰','序號','版本','分支','合併',
    '提交','推送','拉取','克隆','倉庫','儲存庫','本機','遠端','雲端','伺服器','客户端','客戶端','瀏覽器',
    '手機','終端','命令','指令','腳本','脚本','插件','外掛','介面','綁定','異常','上半年','管道','輪子',
    '方案','架構','設計','記錄','日誌','教程','說明','文件','備份','快照','淨','合規',
]
_CJK_SORTED = sorted(set(CJK_COMPOUNDS), key=len, reverse=True)

# 双語向同義詞（查詢 token → 同義 token 集合），提升中英混記召回。
# 借鏡 claude-mem-lite 的 SYNONYM_MAP 手法，精簡為 fixindex 常見詞。
SYNONYMS = {
    '搜尋': {'搜索','檢索','find','查詢'},
    '搜索': {'搜尋','檢索','find','查詢'},
    '查詢': {'查','搜尋','搜索','find'},
    '記憶體': {'內存','ram','memory'},
    '內存': {'記憶體','ram','memory'},
    '修復': {'修補','修','fix','修復'},
    '修': {'修復','fix','patch'},
    '測試': {'test','測試','驗證'},
    '驗證': {'測試','verify','test'},
    '日誌': {'log','logfile','日記'},
    'log': {'日誌','logfile'},
    '錯誤': {'error','報錯','異常'},
    '報錯': {'error','錯誤','異常'},
    '異常': {'error','例外','報錯'},
    '配置': {'config','設定','設置'},
    'config': {'配置','設定','設置'},
    '權限': {'permission','權限'},
    'permission': {'權限'},
    '異常終止': {'crash','崩潰'},
    '崩潰': {'crash','異常終止'},
    'crash': {'崩潰','異常終止'},
    '診斷': {'diagnose','除錯'},
    '除錯': {'debug','診斷'},
    'debug': {'除錯','診斷'},
}

def _cjk_segment(run):
    """字典優先分詞 + bigram fallback，回傳 token list。"""
    toks = []
    i = 0
    while i < len(run):
        matched = False
        for w in _CJK_SORTED:
            if run.startswith(w, i):
                toks.append(w)
                i += len(w)
                matched = True
                break
        if not matched:
            if i + 1 < len(run):
                toks.append(run[i:i+2])   # 疊字 bigram
            i += 1
    return toks

def tokenize(text):
    out = []
    cjk = ''
    en = ''
    for ch in text:
        if re.match(_CJK, ch):
            if en:
                out.append(en.lower()); en = ''
            cjk += ch
        elif ch.isalnum() or ch in '._/@-:#':
            if cjk:
                out.append(cjk); cjk = ''
            en += ch.lower()
        else:
            if en:
                out.append(en.lower()); en = ''
            if cjk:
                out.append(cjk); cjk = ''
    if en:
        out.append(en.lower())
    if cjk:
        out.append(cjk)
    # 把 CJK 連續段切詞：字典優先 + bigram fallback
    final = []
    for t in out:
        if re.fullmatch(_CJK + r'+', t):
            final.extend(_cjk_segment(t))
        else:
            final.append(t)
    return [t for t in final if t]

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
            if len(t) >= 3:
                # prefix-fuzzy: query token may be a prefix of (or contain-segment
                # of) a long camelCase doc token like kIOGPU vs
                # kIOGPUCommandBufferCallbackErrorOutOfMemory. Count occ + small bonus.
                occ = sum(1 for dk in tf if dk.startswith(t) or t.startswith(dk))
                if occ:
                    f = min(occ, 3)
                    s += self.idf(t) * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / max(self.avgdl, 1)))
            if t in tf:
                f = tf[t]
                s += self.idf(t) * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / max(self.avgdl, 1)))
            # synonym expansion: any synonym of this query token also scores (×0.7)
            for syn in SYNONYMS.get(t, ()):
                if syn in tf:
                    s += 0.7 * self.idf(syn) * (tf[syn] * (K1 + 1)) / (tf[syn] + K1 * (1 - B + B * dl / max(self.avgdl, 1)))
        return s

    def search(self, query, limit=8):
        qt = set(tokenize(query))
        scores = [(i, self.score(i, qt)) for i in range(self.n)]
        return sorted([(i, s) for i, s in scores if s > 0], key=lambda x: -x[1])[:limit * 2]

# ── frontmatter 解析：重用 fxmeta（單一解析權威），不再自造 parse_fm ──
import fxmeta

def _parse_file(fp):
    """Return (fm, body_text). Uses fxmeta's authoritative parser."""
    with open(fp) as f:
        txt = f.read()
    fm, bo = fxmeta.parse_frontmatter_full(txt)
    body = txt[bo:] if bo else txt
    return fm, body

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
        fm, body = _parse_file(fp)
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
            entries.append(_build_entry(fid, fn, sn + 1, heading, fm, bi, cont))

        # Fallback: files with frontmatter but no ## § sections (legacy format)
        # get a single whole-body entry so `find` can still reach them.
        if not secs and fm and (fm.get('symptoms') or fm.get('tags') or body.strip()):
            heading = str(fm.get('title') or '(untitled)')
            entries.append(_build_entry(fid, fn, 1, heading, fm, {}, body))
    return entries


def _build_entry(fid, fn, sn, heading, fm, bi, cont):
    toks = []
    # heading 2x
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
    # §4: section-level trust metadata (read-only; legacy → unverified)
    state, last, outcome, ev = fxmeta.section_summary(cont)
    return {
        'key': f'{fid}#{sn}',
        'file': fn,
        'section': f'§{sn}',
        'heading': heading,
        'type': str(fm.get('type') or 'defect'),
        'tokens': toks,
        # trust metadata (may be empty for legacy entries)
        'trust_state': state,
        'last_verified': last,
        'outcome': outcome,
    }


BADGE = {'verified': 'V', 'unverified': 'U', 'stale': 'S', 'blocked': 'B', 'superseded': 'X'}


def _badge(state):
    """One-char trust badge: [V] verified, [U] unverified, [S] stale, [B] blocked, [X] superseded."""
    b = BADGE.get(state, 'U')
    return f'[{b}]'


def main():
    if len(sys.argv) < 2:
        print("usage: fxsearch.py <query> [--limit N] [--all] [--json] [--type defect|insight]", file=sys.stderr)
        sys.exit(1)
    # Walk flags before positional
    args = sys.argv[1:]
    limit = 8
    json_out = False
    etype = None
    q = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--json':
            json_out = True
        elif a == '--limit' and i+1 < len(args):
            limit = int(args[i+1])
            i += 1
        elif a == '--type' and i+1 < len(args):
            etype = args[i+1]
            i += 1
        elif not a.startswith('--'):
            if q is None:
                q = a
        i += 1
    if q is None:
        print("usage: fxsearch.py <query> [--limit N] [--json] [--type defect|insight]", file=sys.stderr)
        sys.exit(1)
    fixdir = os.environ.get('FIXINDEX_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixes')
    entries = build_entries(fixdir)
    if etype:
        entries = [e for e in entries if e['type'] == etype]
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
                 'heading': e['heading'], 'score': round(s, 3),
                 'trust_state': e['trust_state'], 'last_verified': e['last_verified'],
                 'outcome': e['outcome']} for e, s in top]
        print(json.dumps({'query': q, 'hits': hits}, ensure_ascii=False))
    else:
        for e, s in top:
            print(f"  {e['key']:<8} {_badge(e['trust_state'])} {e['section']:<5} ({s:4.2f})  {e['heading']}")
        print(f"\nmatched {len(results)} sections; showing top {len(top)}")


if __name__ == '__main__':
    main()