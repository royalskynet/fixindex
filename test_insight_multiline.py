#!/usr/bin/env python3
"""同一 pipe 多條 INSIGHT: 必須全進 §2，標題取第一條且不切在開括號。

回歸案例 10084／10085：解析用覆寫，兩行 INSIGHT 只留最後一條；
標題又切在「X（」只剩主詞（「自寫 grammy bridge…」）。
"""
import os, subprocess, sys, tempfile
from fxauto import _derive_title

HERE = os.path.dirname(os.path.abspath(__file__))
A = '同機多個 TG bridge 身分（Alice／Heath／Mythos）共用同一份程式碼的正規做法：新實例目錄只把 src 與 node_modules symlink 到既有 bridge，自己擁有 .env。'
B = 'bridge 交給 Claude Code CLI 的 cwd 由環境變數 WELLALLY_PROJECT_ROOT 決定，名字是歷史遺留。'


def test():
    t = _derive_title(A)
    assert t.endswith('正規做法…'), t
    t = _derive_title('自寫 grammy bridge（wellally／mythos 那條）只在需要「以 Claude Code CLI 當身分」時才必要——它的本體是每則訊息 spawn')
    assert '那條' in t, t

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(f'{d}/fixes')
        subprocess.run(['git', 'init', '-q', d], check=True)
        env = dict(os.environ, FIXINDEX_DIR=f'{d}/fixes', FIXINDEX_INDEX=f'{d}/FIX-INDEX.md')
        r = subprocess.run([sys.executable, f'{HERE}/fxauto.py', '--commit'],
                           input=f'INSIGHT: {A}\nINSIGHT: {B}\nRULE: r\nSLUG: multi\n',
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        body = open(f'{d}/fixes/' + [f for f in os.listdir(f'{d}/fixes') if f.endswith('.md')][0]).read()
        assert A in body and B in body, body
        assert body.count('\n  - ') >= 2, body  # 兩條各成一個 symptom


if __name__ == '__main__':
    test()
    print('ok')
