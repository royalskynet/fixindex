#!/usr/bin/env python3
"""fi-signals — /fi 的零 LLM 訊號抽取（借鏡 claude-reflect-system 的 extract_signals：正則抓訊號，主 session 審）。

用法：fi-signals.py <session.jsonl>          印上次 /fi 之後的訊號清單
      fi-signals.py --ack <session.jsonl>    標記已處理到目前行數（/fi 寫完才呼叫）
訊號兩種：ERR＝工具回報失敗（is_error，hook 擋下不算）＋觸發它的指令；USER＝使用者糾正。
標記檔與 fi-run 共用（~/.local/state/fixindex/fi-mark/<sid>），備援掃描不會重掃已處理段。
退出碼：0 有訊號｜5 沒有新內容｜2 用法錯誤
"""
import json
import os
import re
import sys

STATE = os.environ.get('FI_STATE_DIR') or os.path.expanduser('~/.local/state/fixindex/fi-mark')
ERR_RE = re.compile(r'exit code [1-9]|\brc=[1-9]|Error[:\s]|\bFAIL\b|Traceback|not found|No such file|'
                    r'denied|timed? ?out|unbound variable|fatal:', re.I)
# 管線吃掉 rc 時工具不標 is_error，只認這幾種不會出現在正常輸出的字樣
STRONG_RE = re.compile(r'^(fatal:|Traceback \(most recent|.*: unbound variable$|.*: command not found$|.*syntax error)', re.M)
EXIT_RE = re.compile(r'\s*Exit code \d+\s*$')
HOOK_RE =re.compile(r'\s*(PreToolUse|PostToolUse|Stop)\S* hook error')
FIX_RE = re.compile(r'不是|不對|錯了|為什麼又|又忘|別再|不要再|應該是|說過|\bno,|\bwrong\b|\binstead\b', re.I)
MAX = int(os.environ.get('FI_SIGNALS_MAX') or 60)  # ponytail: 超過只留最後 MAX 條；長 session 改跑 fi-run 備援


def one_line(s, n):
    s = ' '.join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + '…'


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
    return ''


def main(argv):
    ack = '--ack' in argv
    args = [a for a in argv if a != '--ack']
    if len(args) != 1 or not os.path.isfile(args[0]):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    path = args[0]
    mark = os.path.join(STATE, os.path.basename(path).rsplit('.', 1)[0])
    with open(path, encoding='utf-8', errors='replace') as fh:
        lines = fh.readlines()
    try:
        start = int(open(mark).read().split()[0])
    except (OSError, ValueError, IndexError):
        start = 0
    if start > len(lines):  # 檔被換掉：從頭
        start = 0
    if ack:
        os.makedirs(STATE, exist_ok=True)
        with open(mark, 'w') as fh:
            fh.write('%d\n' % len(lines))
        return 0
    cmds, out, seen = {}, [], set()
    for no, raw in enumerate(lines[start:], start + 1):
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        msg = d.get('message') or {}
        content = msg.get('content')
        if d.get('type') == 'assistant' and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    inp = b.get('input') or {}
                    cmds[b.get('id')] = inp.get('command') or inp.get('file_path') or b.get('name')
        if d.get('type') != 'user':
            continue
        if isinstance(content, list) and any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
            for b in content:
                if not (isinstance(b, dict) and b.get('type') == 'tool_result'):
                    continue
                body = text_of(b.get('content'))
                # 只收真的失敗；輸出裡碰巧有 FAIL 字樣的不算；hook 擋下是護欄照設計運作，不算經驗
                if HOOK_RE.match(body) or not (b.get('is_error') or STRONG_RE.search(body)):
                    continue
                rest = [l for l in body.splitlines() if l.strip() and not EXIT_RE.match(l)]
                first = next((l for l in rest if ERR_RE.search(l)), rest[0] if rest else body.strip())
                key = one_line(first, 80)
                if key in seen:
                    continue
                seen.add(key)
                out.append('L%d ERR %s ⇒ %s' % (no, one_line(cmds.get(b.get('tool_use_id'), '?'), 120), one_line(first, 160)))
            continue
        said = text_of(content).strip()
        # hook 注入、指令展開、系統通知都不是使用者親口說的
        if (not said or said.startswith('<') or 'SYSTEM NOTIFICATION' in said or d.get('isMeta')
                or d.get('isCompactSummary') or said.startswith('This session is being continued')):
            continue
        if FIX_RE.search(said) and said not in seen:
            seen.add(said)
            out.append('L%d USER %s' % (no, one_line(said, 160)))
    if not out:
        print('fi-signals: 上次 /fi 後沒有新訊號（行 %d→%d）' % (start, len(lines)))
        return 5
    if len(out) > MAX:
        print('（只列最後 %d／%d 條）' % (MAX, len(out)))
        out = out[-MAX:]
    print('\n'.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
