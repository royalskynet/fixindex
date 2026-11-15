#!/usr/bin/env python3
"""一行 %% 分隔的多筆 pipe 走批次：逐筆落地、rc=0（/fi 30 秒內收完）。沒分隔的多筆仍拒收（test_multi_entry_reject）。"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BLK = ("SLUG: zz-alpha\nSYMPTOM: alpha 溢位\nROOT: a\nFIX: a\nVERIFY: a\nRULE: a\n%%\n"
       "SLUG: zz-beta\nSYMPTOM: beta 停滯\nROOT: b\nFIX: b\nVERIFY: b\nRULE: b\n")


def test():
    d = tempfile.mkdtemp()
    env = dict(os.environ, FIXINDEX_DIR=d, FIXINDEX_INDEX=os.path.join(d, 'FIX-INDEX.md'),
               FIXINDEX_NO_SYNC='1')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'fxauto.py'), '--commit'],
                       input=BLK, capture_output=True, text=True, env=env, cwd=d)
    assert r.returncode == 0, (r.returncode, r.stderr[-300:])
    names = sorted(f for f in os.listdir(d) if f[:1].isdigit())
    assert any('zz-alpha' in f for f in names) and any('zz-beta' in f for f in names), names
    assert '"batch": 2' in r.stdout, r.stdout[-300:]
    print("PASS test_batch_sep")


if __name__ == '__main__':
    test()
