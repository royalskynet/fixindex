#!/usr/bin/env python3
"""10138／10139：SLUG 的作用範圍。

10139：pipe 明示 `SLUG: llama-server-...`，title 的 `llama-server` 被切出 `server`，
dash-prefix 命中 0314-server-parser-syntax 被 append 進去。明示 SLUG＝呼叫端已決定
落點：等於既有 slug 才 append 那檔，否則不做字面 domain 猜測。
10138：混合 pipe（SYMPTOM＋INSIGHT）只有一行 SLUG，defect 與 insight 兩筆共用
同一個 slug。SLUG 歸屬它所在的段落；沒有自己 SLUG 的那筆要自己推。
"""
import os, subprocess, sys, tempfile
import fxauto

HERE = os.path.dirname(os.path.abspath(__file__))


def _mk(d, name, title='x'):
    with open(os.path.join(d, name), 'w') as f:
        f.write(f'---\nid: "{name[:4]}"\nslug: {name[5:-3]}\ntitle: {title}\nsymptoms: []\nstatus: active\n---\n# x\n')


def test_explicit_slug_blocks_fuzzy_domain():
    with tempfile.TemporaryDirectory() as d:
        _mk(d, '0314-server-parser-syntax.md')
        _mk(d, '0001-hermes.md')
        old = fxauto.FIXINDEX_DIR
        fxauto.FIXINDEX_DIR = d
        try:
            f = lambda t, s, slug=None: (lambda r: os.path.basename(r) if r else None)(
                fxauto.find_domain_file_auto(t, s, slug=slug))
            t, s = 'llama-server 開著 --reasoning off 仍能開思考', ['llama-server enable_thinking']
            # 明示 SLUG 不等於任何既有 slug → 不猜（10139 重現案例）
            assert f(t, s, 'llama-server-per-request-thinking-budget') is None
            # 明示 SLUG 等於既有領域桶 → 進那個桶
            assert f('任意標題', ['任意'], 'hermes') == '0001-hermes.md'
            # 沒給 SLUG 時維持原行為（不在這裡改 dash-prefix 規則）
            assert f(t, s) == '0314-server-parser-syntax.md'
        finally:
            fxauto.FIXINDEX_DIR = old


def _run(stdin):
    d = tempfile.mkdtemp()
    os.makedirs(f'{d}/fixes')
    subprocess.run(['git', 'init', '-q', d], check=True)
    env = dict(os.environ, FIXINDEX_DIR=f'{d}/fixes', FIXINDEX_INDEX=f'{d}/FIX-INDEX.md')
    r = subprocess.run([sys.executable, f'{HERE}/fxauto.py', '--commit'],
                       input=stdin, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return sorted(f for f in os.listdir(f'{d}/fixes') if f.endswith('.md'))


def test_mixed_pipe_slug_not_shared():
    files = _run('SYMPTOM: plutil replace array index inserts instead of replacing\n'
                 'ROOT: plutil -replace on array index inserts a new element\n'
                 'FIX: use PlistBuddy Set\nVERIFY: plutil -p shows same length\n'
                 'SLUG: plutil-replace-array-index-inserts\nRULE: r\n'
                 'INSIGHT: llama.cpp gemma reasoning off disables thinking server wide\n')
    slugs = [f.split('-', 1)[1] for f in files]
    assert len(files) == 2, files
    assert len(set(slugs)) == 2, files            # 10138：兩筆不得共用 slug
    assert 'plutil-replace-array-index-inserts.md' in slugs, files  # SLUG 歸 defect 段


def test_insight_only_slug_first_still_applies():
    files = _run('SLUG: my-insight\nRULE: r\nINSIGHT: some generalisable insight about queues\n')
    assert files == [files[0]] and files[0].endswith('-my-insight.md'), files


if __name__ == '__main__':
    test_explicit_slug_blocks_fuzzy_domain()
    test_mixed_pipe_slug_not_shared()
    test_insight_only_slug_first_still_applies()
    print('ok slug-scope')
