#!/usr/bin/env python3
"""Slug 取材：ROOT 命名缺陷，title（由 symptom 推導）只命名現象。

真實回歸案例是 9468/9469——當時 slug 從 title 走，產出 cloudflare-waf-403 與
fixindex-doctor-120-timeout-kill，兩個都在命名錯誤訊息。
"""
from fxauto import _slug_source, slugify

def test():
    # 9468 實例：symptom 講 403，root 講「遮罩沒套到鄰居摘錄」
    t = 'Cloudflare WAF 403 只擋某幾筆候選…'
    r = '遮罩只套在候選正文，沒套在同一個 request body 裡的鄰居摘錄（make_body 組的 NEIGHBOUR excerpts）'
    s = slugify(_slug_source(r, t))
    assert 'excerpt' in s or 'neighbour' in s, s
    assert '403' not in s, s

    # 9469 實例
    t = 'fixindex doctor 無參數跑超過 120 秒不回…'
    r = 'doctor 的 _has_vestigial_tag 檢查對每一個 fix 檔 fork 一次 python3 -c'
    s = slugify(_slug_source(r, t))
    assert 'vestigial' in s, s
    assert '120' not in s, s

    # root 缺／untraced → 退回 title，維持原行為
    assert _slug_source('', 'some-title') == 'some-title'
    assert _slug_source('untraced', 'some-title') == 'some-title'
    # 全中文 root 被 NFKD 剝光 → 退回 title
    assert _slug_source('遮罩沒套好', 'some-title') == 'some-title'
    # token 太少不成語意 → 退回 title
    assert _slug_source('doctor 慢', 'some-title') == 'some-title'
    # 開頭純數字 token 丟掉，不產生 NNNN-9212-... 雙編號
    assert _slug_source('9212 killed bash wrapper reaped', 'x') == 'killed-bash-wrapper-reaped'
    # ntok 上限
    assert _slug_source('a b c d e f g h', 'x') == 'a-b-c-d-e'
    print('OK')

if __name__ == '__main__':
    test()
