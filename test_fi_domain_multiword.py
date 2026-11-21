#!/usr/bin/env python3
"""舊介面 `fi <domain>` 的 ② dash-prefix 要比照 fxauto：多詞 slug 至少兩詞命中。

cafd9c6 只修了 fxauto 的 find_domain_file_auto（零參數 fi 走的那條）；
bash 端 find_domain_file（`fi <domain>` 走的）還是單詞打頭就命中多詞 slug，
所以 `fixindex fi session` 會把內容追加進 11415-session-stop-posttooluse-subagentstop，
而且 append 後自動 commit+push —— 錯內容直接上遠端。

修前 / 修後實測（fi session，store 只有 11415-session-stop-posttooluse-subagentstop）：
    修前 appended: 11415-session-stop-posttooluse-subagentstop.md
    修後 created:  11416-session.md
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXINDEX = os.path.join(HERE, 'fixindex')

FM = """---
id: {id}
slug: {slug}
title: "{slug}"
tags: []
symptoms: []
status: active
supersedes: []
related: []
---
# {id} {slug}

## §1 原紀錄

ORIGINAL
"""
PAYLOAD = 'PAYLOAD-LINE'


def store(*slugs):
    """建暫存 store；id 由 1001 起跳。id 一定要四位數，find_domain_file 用
    [0-9][0-9][0-9][0-9]-* glob，三位數的檔案根本掃不到（假通過）。"""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, 'fixes'))
    ids = {}
    for i, slug in enumerate(slugs, start=1001):
        ids[slug] = i
        with open(os.path.join(d, 'fixes', f'{i}-{slug}.md'), 'w', encoding='utf-8') as f:
            f.write(FM.format(id=i, slug=slug))
    return d, ids


def fi(d, domain):
    env = dict(os.environ, FIXINDEX_DIR=os.path.join(d, 'fixes'), FIXINDEX_NO_SYNC='1')
    r = subprocess.run([FIXINDEX, 'fi', domain], input=PAYLOAD + '\n', capture_output=True,
                       text=True, env=env, cwd=d)
    assert 'Traceback' not in r.stdout + r.stderr, r.stdout[-400:] + r.stderr[-400:]
    return r


def appended_files(d):
    out = []
    fixes = os.path.join(d, 'fixes')
    for f in os.listdir(fixes):
        if f.endswith('.md') and PAYLOAD in open(os.path.join(fixes, f), encoding='utf-8').read():
            out.append(f)
    return out


def test():
    # 1) 核心重現：單詞撞多詞 slug，不得追加進既有條目
    d, ids = store('session-stop-posttooluse-subagentstop')
    r = fi(d, 'session')
    victim = f'{ids["session-stop-posttooluse-subagentstop"]}-session-stop-posttooluse-subagentstop.md'
    assert victim not in appended_files(d), ('session 仍誤配多詞 slug', r.stdout[-300:])

    # 2) 回歸：多詞輸入打頭照舊命中（fi session-stop）
    d, ids = store('session-stop-posttooluse-subagentstop')
    r = fi(d, 'session-stop')
    victim = f'{ids["session-stop-posttooluse-subagentstop"]}-session-stop-posttooluse-subagentstop.md'
    assert appended_files(d) == [victim], ('多詞 ② 回歸', r.stdout[-300:])

    # 3) 回歸：確切命中多詞 slug 照舊（fi fix-index → 7001-fix-index）
    d, ids = store('fix-index')
    r = fi(d, 'fix-index')
    assert appended_files(d) == [f'{ids["fix-index"]}-fix-index.md'], ('① 多詞精確命中壞了', r.stdout[-300:])

    # 4) 回歸：單詞 slug 既有桶照舊（fi hermes → 0001-hermes，B1 原案例）
    d, ids = store('hermes')
    r = fi(d, 'hermes')
    assert appended_files(d) == [f'{ids["hermes"]}-hermes.md'], ('單詞 ① 精確命中壞了', r.stdout[-300:])

    # 5) 多詞輸入打頭命中兩檔＝證據不足：兩檔都不得被動到。
    #    只檢既有兩檔——fi 本來就會建新條目，新建檔也在 payload 裡是正常的，
    #    一開始把「有 payload 的檔」全算進來會誤判成誤配。
    d, ids = store('plan-before-code', 'plan-after-code')
    r = fi(d, 'plan-code')
    touched = [f for f in appended_files(d) if f in {f'{i}-{s}.md' for s, i in ids.items()}]
    assert touched == [], ('多檔 ② 仍誤配', r.stdout[-300:])

    print('PASS test_fi_domain_multiword')


if __name__ == '__main__':
    test()
