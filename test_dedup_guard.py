#!/usr/bin/env python3
"""Dedup floors in fxauto.find_duplicate (fix 9299).

Guards the 2026-09-21 misfire: stub title「沙箱內 python3…」(3 tokens) got
auto-superseded by an unrelated entry sharing only 沙箱 — which the CJK bigram
tokenizer counts twice (沙箱 + 箱內), pushing the ratio to 0.67 > 0.6.
"""
import fxauto

T = fxauto._title_tokens


def would_fire(old, new):
    return fxauto._dup_fires(T(old), T(new))


def test():
    # the actual misfire: unrelated, one shared word split into two bigrams
    assert not would_fire("沙箱內 python3 CERTIFICATE_VERIFY_FAILED",
                          "沙箱內 git post-commit 靜默失敗導致安裝副本落後 HEAD")
    # truncated stubs are dumping grounds: 0836「deepclaude…」collected 19 links
    assert not would_fire("deepclaude…", "deepclaude 換 router 後模型名不被辨識")
    # truncated NEW title naming only product+version+OS is a subset of any
    # entry about that product — 9574 (gateway auth) wrongly superseded 9572
    assert not would_fire("Windows 無頭機裝 OpenClaw 2026.9.6 要求 Node ≥24.16…",
                          "OpenClaw 2026.9.6（Windows…")
    # a genuine restatement still dedups
    assert would_fire("launchctl bootout 裸 domain 拆掉整個登入 session",
                      "launchctl bootout 裸 domain 會拆掉整個登入 session 無頭機無法自救")
    print("PASS test_dedup_guard")


if __name__ == "__main__":
    test()
