#!/usr/bin/env python3
"""10195：指令欄位不該被自由文字容錯撿成 symptom。

無 `SYMPTOM:` 時 parser 取首行非 KEY 行當 symptom，但白名單只列了
symptom/root/fix/verify 四個，且 regex `^[A-Z]+\\s*:` 不含 `-`。於是
`EVIDENCE: log` 被用兩次——正確解析成 Evidence，又整行（含 KEY 前綴）
撿成 symptom，污染 title／slug／frontmatter，再補 untraced／applied 填充值。
`REVISIT-WHEN:` 連白名單都進不去。

修法：RECOGNISED_KEYS 單一來源，主迴圈與容錯共用；全是指令欄位的 pipe
找不到 symptom 候選，落到既有的 SYMPTOM required 而不是硬撿一行。
"""
import os, re, subprocess, sys, tempfile
import fxauto

HERE = os.path.dirname(os.path.abspath(__file__))


def _run(stdin):
    d = tempfile.mkdtemp()
    os.makedirs(f'{d}/fixes')
    subprocess.run(['git', 'init', '-q', d], check=True)
    env = dict(os.environ, FIXINDEX_DIR=f'{d}/fixes', FIXINDEX_INDEX=f'{d}/FIX-INDEX.md')
    r = subprocess.run([sys.executable, f'{HERE}/fxauto.py', '--commit'],
                       input=stdin, capture_output=True, text=True, env=env)
    sympt = None
    for f in sorted(os.listdir(f'{d}/fixes')):
        if f.endswith('.md'):
            m = re.search(r'^## §1 Symptom\n\n(.*)', open(f'{d}/fixes/{f}').read(), re.M)
            sympt = m.group(1) if m else '(insight)'
            break
    return r.returncode, sympt


def test_command_keys_never_become_symptom():
    # 全是指令欄位、沒有自由文字 → 拒絕，不要硬撿一行當 symptom
    for pipe in ('SLUG: my-test-slug\nRULE: r\n',
                 'EVIDENCE: log line here\nRULE: r\n',
                 'REVISIT-WHEN: next month\nRULE: r\n',   # 舊 regex 漏掉的 dash KEY
                 'QUERIES: q\nTYPE: insight-ish\nRULE: r\n'):
        rc, sympt = _run(pipe)
        assert rc == 1, f'應被 SYMPTOM required 擋下: {pipe!r} -> rc={rc} sympt={sympt!r}'


def test_free_text_fallback_still_works():
    # 容錯本身不能壞：無 SYMPTOM KEY 時首行自由文字仍是 symptom
    rc, sympt = _run('free text symptom line\nROOT: r\nFIX: f\nVERIFY: v\nRULE: r\n')
    assert rc == 0 and sympt == 'free text symptom line', (rc, sympt)
    # 未列入 RECOGNISED_KEYS 的 KEY 行照舊當自由文字（主迴圈也走 detail_lines）
    rc, sympt = _run('NOTE: this is free text\nROOT: r\nFIX: f\nVERIFY: v\nRULE: r\n')
    assert rc == 0 and sympt == 'NOTE: this is free text', (rc, sympt)


def test_explicit_symptom_unaffected():
    rc, sympt = _run('SYMPTOM: real symptom here\nROOT: r\nFIX: f\nVERIFY: v\n'
                     'SLUG: ok-slug\nRULE: r\n')
    assert rc == 0 and sympt == 'real symptom here', (rc, sympt)


def test_recognised_keys_covers_main_loop():
    # 兩處漂移是這個 bug 的根因：主迴圈認得的 KEY 必須全在常數裡。
    # 主迴圈對未識別 KEY 有 assert，這裡釘住常數內容本身。
    assert fxauto.RECOGNISED_KEYS >= {
        'symptom', 'root', 'fix', 'verify', 'evidence',
        'context', 'insight', 'implication', 'revisit-when',
        'queries', 'type', 'slug', 'rule',
    }
    assert fxauto.KEY_LINE_RE.match('REVISIT-WHEN: x').group(1) == 'REVISIT-WHEN'


if __name__ == '__main__':
    test_command_keys_never_become_symptom()
    test_free_text_fallback_still_works()
    test_explicit_symptom_unaffected()
    test_recognised_keys_covers_main_loop()
    print('ok key-not-symptom')
