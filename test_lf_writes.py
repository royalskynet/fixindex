#!/usr/bin/env python3
"""fxauto text writes must pin newline='\\n' and encoding='utf-8' (2026-09-26).

fix-store is shared across the fleet. On Windows, text-mode open() translates
\\n to CRLF and defaults to the locale codec (cp950), so `fixindex fi` pushed 10
CRLF files — two of them pre-existing entries rewritten whole — into the store.
"""
import os
import re

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fxauto.py')


def test():
    src = open(SRC, encoding='utf-8').read()
    bad = []
    for m in re.finditer(r"(?<![.\w])open\(([^()]*)\)", src):
        args = m.group(1)
        line = src.count('\n', 0, m.start()) + 1
        if "encoding='utf-8'" not in args:
            bad.append((line, 'no encoding'))
        if re.search(r",\s*'[wa]\+?'", args) and "newline='\\n'" not in args:
            bad.append((line, 'write without newline'))
    assert not bad, bad
    print("PASS test_lf_writes")


if __name__ == "__main__":
    test()
