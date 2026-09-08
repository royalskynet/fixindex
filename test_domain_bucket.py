#!/usr/bin/env python3
"""0853: 裸詞 slug 領域桶只認 title token；symptom 順帶提到桶名不得吸走整條。"""
import os, tempfile, fxauto


def _mk(d, name, title):
    with open(os.path.join(d, name), 'w') as f:
        f.write(f'---\nid: "{name[:4]}"\nslug: {name[5:-3]}\ntitle: {title}\nsymptoms: []\nstatus: active\n---\n# x\n')


def demo():
    with tempfile.TemporaryDirectory() as d:
        _mk(d, '0001-hermes.md', 'hermes bucket')
        _mk(d, '0619-fixindex-fi-append.md', 'fixindex fi append')
        old = fxauto.FIXINDEX_DIR
        fxauto.FIXINDEX_DIR = d
        try:
            f = lambda t, s: (lambda r: os.path.basename(r) if r else None)(fxauto.find_domain_file_auto(t, s))
            # symptom 順帶提到 hermes → 不進桶（0853 的重現案例）
            assert f('obsidian-mcp 孤兒 ppid=1', ['父 process 是 hermes gateway']) is None
            # title 明講 hermes → 進桶（領域桶的本意）
            assert f('hermes gateway 401', ['bot 沉默']) == '0001-hermes.md'
            # 多詞 slug 不受影響：symptom token 仍可 ① 精確命中
            assert f('無關標題', ['fixindex-fi-append 出錯']) == '0619-fixindex-fi-append.md'
        finally:
            fxauto.FIXINDEX_DIR = old
    print('ok domain-bucket')


if __name__ == '__main__':
    demo()
