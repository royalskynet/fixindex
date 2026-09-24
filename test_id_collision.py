#!/usr/bin/env python3
"""多裝置撞號：本機新建的條目跟他機同號時改號，他機那份不動。

配號鎖是本機 flock，鎖不住第二台機器。兩台各自 pull-first 後在同一個 max 上
配號 → 先 push 的贏，後到的 rebase 完會拿到兩個 NNNN-*.md（檔名不同，git 不
報衝突），所以撞號要靠掃描發現。
"""
import os, tempfile, fxauto


def _mk(d, name, body='', related=''):
    fid = name[:4]
    rel = f'related: [{related}]\n' if related else 'related: []\n'
    with open(os.path.join(d, name), 'w') as f:
        f.write(f'---\nid: "{fid}"\nslug: {name[5:-3]}\ntitle: t\nsymptoms: []\n'
                f'status: active\nsupersedes: []\n{rel}---\n\n# {fid} t\n\n{body}')
    return os.path.join(d, name)


def test():
    with tempfile.TemporaryDirectory() as d:
        old_dir, old_idx = fxauto.FIXINDEX_DIR, fxauto._run_index
        fxauto.FIXINDEX_DIR = d
        fxauto._run_index = lambda *a, **k: None   # re-index 不在本測試範圍
        try:
            _mk(d, '0001-unrelated.md')
            theirs = _mk(d, '0003-theirs.md')          # 他機先 push，保住 0003
            mine = _mk(d, '0003-mine.md', body='port 0003 是正文提到的數字，不該被換')
            # 同一次寫入的另一個檔，related 指向我這份
            sibling = _mk(d, '0002-sibling.md', related='"0003"')

            renames = {}
            out = fxauto.resolve_id_collision([mine, sibling], renames)

            new = os.path.join(d, '0004-mine.md')
            assert os.path.exists(new), os.listdir(d)
            assert not os.path.exists(mine)
            assert os.path.exists(theirs), '他機那份不得被動到'
            txt = open(new).read()
            assert 'id: "0004"' in txt, txt
            assert '# 0004 t' in txt, txt
            assert 'port 0003 是正文' in txt, '正文裡的數字不是 id，不該換'
            assert 'related: ["0004"]' in open(sibling).read()
            assert new in out and sibling in out, out
            # 舊路徑要留在 paths 裡：git add 收到它才會 stage 那筆刪除，
            # 否則 commit 只加新檔，遠端同時留著新舊兩份（two-device 沙箱實測過）
            assert mine in out, out
            assert renames == {mine: new}, renames
            # 他機那份的 frontmatter 原封不動
            assert 'id: "0003"' in open(theirs).read()

            # symlink 路徑不得把自己誤當「他機那份」：glob 走真實路徑、
            # paths 走 symlink 路徑時，abspath 比不掉自己 → 沒撞號也改號
            link = os.path.join(tempfile.gettempdir(), 'fxlink-%d' % os.getpid())
            os.symlink(d, link)
            try:
                solo_link = os.path.join(link, '0008-viasymlink.md')
                _mk(d, '0008-viasymlink.md')
                r3 = {}
                assert fxauto.resolve_id_collision([solo_link], r3) == [solo_link], r3
                assert r3 == {}, r3
                assert os.path.exists(os.path.join(d, '0008-viasymlink.md'))
            finally:
                os.unlink(link)

            # 沒撞號 → 原樣回傳，不改名
            solo = _mk(d, '0009-solo.md')
            r2 = {}
            assert fxauto.resolve_id_collision([solo], r2) == [solo]
            assert r2 == {}
            assert os.path.exists(solo)
        finally:
            fxauto.FIXINDEX_DIR, fxauto._run_index = old_dir, old_idx
    print('OK')


if __name__ == '__main__':
    test()
