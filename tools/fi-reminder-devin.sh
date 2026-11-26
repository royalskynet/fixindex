#!/usr/bin/env bash
# fi-reminder-devin.sh — Devin Stop hook（advisory，不 block、永不非零退出）。
# 兩件事：
#   1. 本 session 上次 /fi 之後還有未處理的除錯／糾正訊號（fi-signals-devin rc=0）→ 提醒跑 /fi。
#   2. fixindex 有未同步積壓（status --assert-clean ≠0）→ 提醒補推。
# 對應 cc 版 ~/.claude/hooks/fi-reminder.sh（那版吃 Claude Code jsonl＋可 block，這版只提示）。
# 主體用 python 不用 shell 邏輯：hook 環境精簡（PATH/HOME 不定、bash 3.2），
# shell 版 set -u／glob／指令缺失的行為不可預期，曾造成 Stop hook 反覆 exit 1（2026-11-26）。
export INPUT="$(cat 2>/dev/null)"
python3 - <<'PYEOF'
import json, os, subprocess, sys, glob

def main():
    try:
        d = json.loads(os.environ.get('INPUT') or '') or {}
    except Exception:
        d = {}
    sid = d.get('session_id') or ''
    home = os.path.expanduser('~')
    tdir = os.path.join(home, '.local/share/devin/cli/transcripts')

    transcript = None
    try:
        files = sorted(glob.glob(os.path.join(tdir, '*.json')), key=os.path.getmtime, reverse=True)
        if sid:
            needle = '"%s"' % sid
            for f in files:
                try:
                    with open(f, 'r', errors='replace') as fh:
                        if needle in fh.read():
                            transcript = f
                            break
                except Exception:
                    continue
        if not transcript and files:
            transcript = files[0]
    except Exception:
        transcript = None
    if not transcript:
        return

    msgs = []
    try:
        sig = subprocess.run(
            ['python3', os.path.join(home, 'dev/fixindex/tools/fi-signals-devin.py'), transcript],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if sig.returncode == 0:
            msgs.append('本 session 有未處理的除錯／使用者糾正訊號：建議跑 fi 流程回顧，值得記的寫進 fixindex')
    except Exception:
        pass

    fixindex = os.path.join(home, '.local/bin/fixindex')
    if os.path.isfile(fixindex):
        try:
            st = subprocess.run([fixindex, 'status', '--assert-clean'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            if st.returncode != 0:
                msgs.append('fixindex 有未同步積壓（離線或 push 失敗），收尾前補推')
        except Exception:
            pass

    if not msgs:
        return
    m = '；'.join(msgs)
    print(json.dumps({'systemMessage': m,
                      'hookSpecificOutput': {'hookEventName': 'Stop', 'additionalContext': m}},
                     ensure_ascii=False))

try:
    main()
except Exception:
    pass
sys.exit(0)
PYEOF
exit 0
