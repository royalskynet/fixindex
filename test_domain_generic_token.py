#!/usr/bin/env python3
"""Generic markers (Bash / pure / read…) must not route an entry into a domain bucket.

Guards the 2026-10-26 misfire: a 「純讀檔被 LSP-FIRST hook 擋」 symptom was
appended twice into 9907-bash.md — a hand-made admin bucket (`9907-bash`,
bare slug) whose name matches the tool the symptom mentions, not the defect.
"""
import os
import tempfile

import fxauto


def test_tokens_drop_generic():
    toks = fxauto._word_tokens("pure-read Bash hook blocks Read tool")
    assert 'bash' not in toks and 'read' not in toks and 'pure' not in toks, toks
    assert 'hook' not in toks and 'tool' not in toks, toks
    # fixindex 本身是工具名：整份 fixes/ 沒有一個『領域』叫 fixindex，命中的是雜記桶
    assert 'fixindex' not in fxauto._word_tokens("fixindex fi 多段 KEY 區塊被併成 §N")
    # 帶具體後綴的 fixindex-xxx 是領域詞，保留（0199）
    assert 'fixindex' in fxauto._word_tokens("fixindex-fi-append 出錯")
    # an all-generic text still returns something so matching does not vanish
    assert fxauto._word_tokens("Bash read") != []


def test_no_append_to_bare_admin_bucket():
    tmp = tempfile.mkdtemp()
    for name, slug, title in (('9907-bash.md', 'bash', 'Bash'),
                              ('9777-fixindex.md', 'fixindex', 'fixindex 雜記')):
        with open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
            f.write(f'---\nid: "{name[:4]}"\nslug: {slug}\ntitle: "{title}"\nstatus: active\n---\n\n'
                    f'## §1 記錄\n\n{title}\n')
    old = fxauto.FIXINDEX_DIR
    fxauto.FIXINDEX_DIR = tmp
    try:
        for symp in ("Bash hook blocks a pure read: Bash",
                     "fixindex fi batches multi-block KEY input into one section"):
            m = fxauto.find_domain_file_auto(symp, [symp])
            assert m is None, (symp, m)
    finally:
        fxauto.FIXINDEX_DIR = old
    print("PASS test_domain_generic_token")


if __name__ == '__main__':
    test_tokens_drop_generic()
    test_no_append_to_bare_admin_bucket()
