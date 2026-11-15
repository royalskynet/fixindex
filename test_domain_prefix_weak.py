#!/usr/bin/env python3
"""② dash-prefix 要至少兩個 slug 詞命中：12174 的「session」被吸進 11415-session-stop-…。"""
import os, tempfile
import fxauto


def test():
    d = tempfile.mkdtemp()
    for name in ('11415-session-stop-posttooluse-subagentstop.md', '0500-oc-headless-retry.md'):
        with open(os.path.join(d, name), 'w') as f:
            f.write(f'---\nid: "{name.split("-")[0]}"\nslug: {name.split("-", 1)[1][:-3]}\ntitle: x\nstatus: active\n---\n# x\n')
    old, fxauto.FIXINDEX_DIR = fxauto.FIXINDEX_DIR, d
    try:
        f = lambda t: (lambda r: os.path.basename(r) if r else None)(fxauto.find_domain_file_auto(t, [t]))
        assert f('/fi 已定為主 session 就地跑，記憶規則把它派 od') is None
        # 兩個 slug 詞都在 → 仍命中
        assert f('session stop hook 沒觸發') == '11415-session-stop-posttooluse-subagentstop.md'
    finally:
        fxauto.FIXINDEX_DIR = old
    print('PASS test_domain_prefix_weak')


if __name__ == '__main__':
    test()
