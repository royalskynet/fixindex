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
    # an all-generic text still returns something so matching does not vanish
    assert fxauto._word_tokens("Bash read") != []


def test_no_append_to_bare_admin_bucket():
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, '9907-bash.md'), 'w', encoding='utf-8') as f:
        f.write('---\nid: "9907"\nslug: bash\ntitle: "Bash"\nstatus: active\n---\n\n'
                '## §1 記錄\n\nBash 雜記\n')
    old = fxauto.FIXINDEX_DIR
    fxauto.FIXINDEX_DIR = tmp
    try:
        symp = "Bash hook blocks a pure read: Bash"
        m = fxauto.find_domain_file_auto(symp, [symp])
        assert m is None, m
    finally:
        fxauto.FIXINDEX_DIR = old
    print("PASS test_domain_generic_token")


if __name__ == '__main__':
    test_tokens_drop_generic()
    test_no_append_to_bare_admin_bucket()
