#!/usr/bin/env python3
"""verified_on frontmatter stamp in fxauto.build_entry / build_entry_insight.

對應 issue royalskynet/fixindex#9 建議 1：自動蓋章不靠寫入者自律。
"""
import re
import fxauto


def test():
    entry = fxauto.build_entry('0001', 'title', ['symp'], 'root', 'fix', 'verify', 'slug')
    insight = fxauto.build_entry_insight('0002', 'title', 'ctx', 'ins', 'impl', 'revisit',
                                          'slug', ['q'])
    pat = re.compile(r'^verified_on: \S+ \d{4}-\d{2}-\d{2}$', re.M)
    for out in (entry, insight):
        assert pat.search(out), f'missing verified_on line in:\n{out}'
        assert 'related: []' in out
        assert 'status: active' in out
    print("PASS test_verified_on")


if __name__ == "__main__":
    test()
