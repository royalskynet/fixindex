#!/usr/bin/env python3
"""ID 至少 4 位數、可以長到 5 位以上（同 adr-tools：數值取 max，%04d 只是最小寬度）。

舊版兩個坑：字典序 sorted() 讓 '9999-*' 排在 '10000-*' 後面，每次都配 10000 而撞號；
[:4] 把 10000 截成 1000，跟既有的 1000-* 混在一起。
"""
import os, tempfile, fxauto, fxmeta, fxsearch


def _mk(d, name):
    fid = name.split('-', 1)[0]
    with open(os.path.join(d, name), 'w') as f:
        f.write(f'---\nid: "{fid}"\nslug: {name[len(fid)+1:-3]}\ntitle: t{fid}\nsymptoms: []\n'
                f'status: active\n---\n\n# {fid} t{fid}\n\n## 1. Symptom\n\nzzuniq{fid}\n')


def test():
    with tempfile.TemporaryDirectory() as d:
        old = fxauto.FIXINDEX_DIR
        fxauto.FIXINDEX_DIR = d
        try:
            for n in ('0001-a.md', '1000-b.md', '9999-e.md'):
                _mk(d, n)
            assert fxauto._scan_next_id() == '10000', fxauto._scan_next_id()
            _mk(d, '10000-f.md')
            assert fxauto._scan_next_id() == '10001', fxauto._scan_next_id()
            # 5 位數不得被截成 4 位、跟 1000-* 混淆
            assert fxmeta.SECTION_KEY.match('10000#1').group(1) == '10000'
            ids = {e['file'].split('-', 1)[0] for e in fxsearch.build_entries(d)}

            if ids is not None:
                assert '10000' in ids and '1000' in ids, ids
        finally:
            fxauto.FIXINDEX_DIR = old
    print('test_id_overflow ok')


if __name__ == '__main__':
    test()
