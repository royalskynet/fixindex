#!/usr/bin/env python3
"""同輪去重檢查：同主題不同措辭要判重，不同主題不可誤判。

真實校準資料（2026-11-12 那一輪）：該判重的 6 組落在 0.85–1.00，
存活的 6 條彼此最高 0.25，所以門檻取 0.6。
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, 'tools', 'fi-dup-check.py')

ENTRIES = {
    # 同主題、不同措辭（仿 12028/12029/12032）
    '9001': '由動作產生的檢查（sha、diff）才能擋失敗；echo「已保留」只是動作的裝飾，與 rc 無關',
    '9002': '由動作產生的檢查（sha、diff）才能擋失敗；echo「已保留」只是裝飾，與 rc 無關',
    # 不同主題（仿 12023 / 12026）
    '9003': 'deepclaude 隔離實例的 settings 被 dc-sync-main 帶進 apiKeyHelper',
    '9004': 'delegate-guard 達門檻後要加註解才能在主 session 繼續做',
}


def run(tmp, ids, *extra):
    env = dict(os.environ, FIXINDEX_DIR=tmp)
    return subprocess.run([sys.executable, CHECK, *extra, *ids],
                          capture_output=True, text=True, env=env)


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        for fid, title in ENTRIES.items():
            with open(os.path.join(tmp, f'{fid}-slug.md'), 'w', encoding='utf-8') as f:
                f.write(f'---\nid: {fid}\ntitle: {title}\n---\n\n## §1 Symptom\n\n內文\n')

        r = run(tmp, ['9001', '9002'])
        if r.returncode != 1:
            fails.append(f'同主題改寫應判重，rc={r.returncode} out={r.stdout!r}')

        r = run(tmp, ['9003', '9004'])
        if r.returncode != 0:
            fails.append(f'不同主題不該判重，rc={r.returncode} out={r.stdout!r}')

        r = run(tmp, ['9001', '9003', '9004'])
        if r.returncode != 0:
            fails.append(f'單一條目不該與他人判重，rc={r.returncode} out={r.stdout!r}')

        r = run(tmp, ['9001', '9002', '9003', '9004'])
        if r.returncode != 1 or '9001' not in r.stdout:
            fails.append(f'混合情形應指出 9001/9002，rc={r.returncode} out={r.stdout!r}')

        r = run(tmp, ['9999'])
        if r.returncode != 2:
            fails.append(f'找不到條目應 rc=2，實得 {r.returncode}')

        r = run(tmp, ['9001', '9002'], '--threshold', '1.1')
        if r.returncode != 0:
            fails.append('門檻拉到 1.1 時不該判重')

    if fails:
        for f in fails:
            print('FAIL:', f)
        sys.exit(1)
    print('PASS test_fi_dup_check')


if __name__ == '__main__':
    main()
