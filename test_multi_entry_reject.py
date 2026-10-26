#!/usr/bin/env python3
"""多筆 KEY 區塊一次 pipe 要拒收（11472/11476/11479/11480 同一教訓被重記四次）。

舊行為：SYMPTOM 第一筆贏、SLUG 最後一筆贏，揉成一筆、其餘靜默丟、exit 0。
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BLK = ("SLUG: zz-alpha\nSYMPTOM: alpha 溢位\nROOT: a\nFIX: a\nVERIFY: a\nRULE: a\n\n"
       "SLUG: zz-beta\nSYMPTOM: beta 停滯\nROOT: b\nFIX: b\nVERIFY: b\nRULE: b\n")


def run(stdin):
    d = tempfile.mkdtemp()
    env = dict(os.environ, FIXINDEX_DIR=d, FIXINDEX_NO_SYNC='1')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'fxauto.py'), '--shadow'],
                       input=stdin, capture_output=True, text=True, env=env, cwd=d)
    return r, os.listdir(d)


def test():
    r, files = run(BLK)
    assert r.returncode == 2, (r.returncode, r.stderr[-300:])
    assert 'MULTI-ENTRY' in r.stderr, r.stderr[-300:]
    assert not [f for f in files if f.endswith('.md') and f[:1].isdigit()], files
    # insight 段同類：兩筆 INSIGHT 各帶 SLUG 也會被併成一筆
    r, _ = run("INSIGHT: x 洞見\nSLUG: zz-ins-a\n\nINSIGHT: y 洞見\nSLUG: zz-ins-b\n")
    assert r.returncode == 2 and 'MULTI-ENTRY' in r.stderr, (r.returncode, r.stderr[-300:])
    # 單筆照常可過（不得被誤擋）
    one = BLK.split('\n\n')[0] + '\n'
    r, _ = run(one)
    assert r.returncode == 0, (r.returncode, r.stderr[-300:])
    print("PASS test_multi_entry_reject")


if __name__ == '__main__':
    test()
