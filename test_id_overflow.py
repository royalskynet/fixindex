#!/usr/bin/env python3
"""ID 是 4 位數（全庫 15+ 處 [:4]／\\d{4}），配到 9999 之後不能給 10000。

舊版用字典序 sorted()：'9999-*' 排在 '10000-*' 後面，每次都配 10000 → 連續撞號，
而且 [:4] 把 10000 截成 1000，跟既有的 1000-* 混在一起。
"""
import os, tempfile, fxauto


def test():
    with tempfile.TemporaryDirectory() as d:
        old = fxauto.FIXINDEX_DIR
        fxauto.FIXINDEX_DIR = d
        try:
            for n in ('0001-a', '1000-b', '1001-c', '9998-d', '9999-e'):
                open(os.path.join(d, n + '.md'), 'w').close()
            assert fxauto._scan_next_id() == '1002', fxauto._scan_next_id()
            open(os.path.join(d, '1002-f.md'), 'w').close()
            assert fxauto._scan_next_id() == '1003'
            # 未滿 9999 時照舊 max+1，不回頭補洞
            os.remove(os.path.join(d, '9999-e.md'))
            assert fxauto._scan_next_id() == '9999'
        finally:
            fxauto.FIXINDEX_DIR = old
    print('test_id_overflow ok')


if __name__ == '__main__':
    test()
