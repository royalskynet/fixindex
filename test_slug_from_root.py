#!/usr/bin/env python3
"""Slug 取材：ROOT 命名缺陷，title（由 symptom 推導）只命名現象。

真實回歸案例是 9468/9469——當時 slug 從 title 走，產出 cloudflare-waf-403 與
fixindex-doctor-120-timeout-kill，兩個都在命名錯誤訊息。9474 是第二輪回歸：
ROOT 是中文敘述夾雜模組名時，硬抽 ascii token 得到 shim-yaml-yaml-xml-parsers，
零散識別字拼不成短語——這種要標 title-weak 讓呼叫端自己給 SLUG:。
"""
from fxauto import _slug_source, _slug_pick, slugify


def test():
    # 9468 實例：symptom 講 403，root 講「遮罩沒套到鄰居摘錄」
    t = 'Cloudflare WAF 403 只擋某幾筆候選…'
    r = '遮罩只套在候選正文，沒套在同一個 request body 裡的鄰居摘錄（make_body 組的 NEIGHBOUR excerpts）'
    src, kind = _slug_source(r, t)
    assert kind == 'root', (kind, src)
    s = slugify(src)
    assert 'excerpt' in s or 'neighbour' in s, s
    assert '403' not in s, s

    # 9469 實例
    t = 'fixindex doctor 無參數跑超過 120 秒不回…'
    r = 'doctor 的 _has_vestigial_tag 檢查對每一個 fix 檔 fork 一次 python3 -c'
    src, kind = _slug_source(r, t)
    assert kind == 'root', (kind, src)
    s = slugify(src)
    assert 'vestigial' in s, s
    assert '120' not in s, s

    # 9474 實例：中文為主的長 ROOT，ascii 只是零星模組名 → title-weak
    r = ('shim 的觸發條件只探測一個依賴模組（yaml），但它要保護的失效面是兩個'
         '（yaml 與 xml.parsers.expat）。yaml 是症狀最先冒出來的地方，pyexpat 才是'
         '根因；用症狀當守門條件，於是症狀被單獨修掉之後，守門就永遠開著。')
    src, kind = _slug_source(r, 'some-title')
    assert kind == 'title-weak', (kind, src)
    assert src == 'some-title', src

    # 重複 token 去掉（保序）——否則 ROOT 裡反覆出現的模組名拼成 yaml-yaml-xml
    src, kind = _slug_source('yaml probe yaml xml expat gate', 'x')
    assert src == 'yaml-probe-xml-expat-gate', src

    # root 缺／untraced → 退回 title，維持原行為
    assert _slug_source('', 'some-title') == ('some-title', 'title')
    assert _slug_source('untraced', 'some-title') == ('some-title', 'title')
    # 全中文 root 被 NFKD 剝光 → 退回 title
    assert _slug_source('遮罩沒套好', 'some-title') == ('some-title', 'title')
    # token 太少不成語意 → 退回 title
    assert _slug_source('doctor 慢', 'some-title') == ('some-title', 'title')
    # 開頭純數字 token 丟掉，不產生 NNNN-9212-... 雙編號
    assert _slug_source('9212 killed bash wrapper reaped', 'x')[0] == 'killed-bash-wrapper-reaped'
    # ntok 上限
    assert _slug_source('a b c d e f g h', 'x')[0] == 'a-b-c-d-e'

    # SLUG: 明示一律最優先，連 title-weak 的路徑都不會走到
    assert _slug_pick('shim probe misses pyexpat', r, 'some-title') == (
        'shim-probe-misses-pyexpat', 'explicit')
    print('OK')


if __name__ == '__main__':
    test()
