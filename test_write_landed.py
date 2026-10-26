#!/usr/bin/env python3
"""寫入工具的通用防呆（11481：工具回報成功、內容卻被丟 → agent 重寫重記陷入迴圈）。

1. 落地檢查：輸入的欄位找不到就還原＋非零退出，不准 exit 0。
2. dedup（supersede）路徑不得丟 RULE（defect、insight 兩條都測）。
3. 迴圈警告：最近窗內已寫過相近教訓 → stderr＋payload 出聲，但照樣寫入。
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFECT = ("SLUG: zz-probe-dup\nSYMPTOM: zz 探針寫入後欄位被靜默丟失\nROOT: zz 根因甲\n"
          "FIX: zz 修法甲\nVERIFY: zz 驗收甲\nRULE: zz 規則{}{}{}{}{}{}{}{}{}{}{}{}\n")
INSIGHT = ("TYPE: insight\nSLUG: zz-ins-dup\nCONTEXT: zz 情境寫入工具回報成功但欄位遺失\n"
           "INSIGHT: zz 寫入後要讀回比對每個欄位才算落地\nRULE: zz 洞見規則{}{}{}{}{}{}{}{}{}{}{}{}\n")


def run(d, stdin):
    env = dict(os.environ, FIXINDEX_DIR=os.path.join(d, 'fixes'), FIXINDEX_NO_SYNC='1')
    return subprocess.run([sys.executable, os.path.join(HERE, 'fxauto.py'), '--commit'],
                          input=stdin, capture_output=True, text=True, env=env, cwd=d)


def mds(d):
    f = os.path.join(d, 'fixes')
    return sorted(x for x in os.listdir(f) if x.endswith('.md'))


def body(d, name):
    return open(os.path.join(d, 'fixes', name), encoding='utf-8').read()


def check_dedup_keeps_rule(tpl, label):
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'fixes'))
    r1 = run(d, tpl.format(*'甲' * 12))
    assert r1.returncode == 0, (label, r1.stderr[-400:])
    assert 'LOOP-WARNING' not in r1.stderr, (label, '首筆不該警告', r1.stderr[-300:])
    r2 = run(d, tpl.format(*'乙' * 12))
    assert r2.returncode == 0, (label, r2.stderr[-400:])
    assert '"dedup": true' in r2.stdout, (label, '沒走到 dedup 路徑', r2.stdout[-300:])
    newest = mds(d)[-1]
    assert '乙乙乙乙' in body(d, newest), (label, 'dedup 路徑把 RULE 丟了', newest)
    # 3. 迴圈警告：同一教訓 2h 內第二次寫 → 出聲但照寫（rc 0 已驗）
    assert 'LOOP-WARNING' in r2.stderr and 'loop_warning' in r2.stdout, (label, r2.stderr[-300:])


def check_verify_rejects_missing_field():
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'fixes'))
    os.environ['FIXINDEX_DIR'] = os.path.join(d, 'fixes')
    sys.path.insert(0, HERE)
    import fxauto
    p = os.path.join(d, 'fixes', '0001-x.md')
    open(p, 'w').write('---\nid: "0001"\n---\n# x\nROOT: 有\n')
    try:
        fxauto._verify_written(p, expect={'root': '有', 'rule': '這條規則沒落地'})
    except SystemExit as e:
        assert e.code not in (0, None), e.code
        assert not os.path.exists(p), '欄位沒落地時新檔要刪掉'
    else:
        raise AssertionError('欄位沒落地卻沒非零退出')
    open(p, 'w').write('---\nid: "0001"\n---\n# x\nROOT: 有\n')
    fxauto._verify_written(p, expect={'root': '有', 'rule': ''})   # 空值不算缺
    assert os.path.exists(p)


def test():
    check_verify_rejects_missing_field()
    check_dedup_keeps_rule(DEFECT, 'defect')
    check_dedup_keeps_rule(INSIGHT, 'insight')
    print("PASS test_write_landed")


if __name__ == '__main__':
    test()
