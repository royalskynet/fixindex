#!/usr/bin/env python3
"""fi-signals-devin — /fi 訊號抽取的 Devin CLI 版（對應 fi-signals.py 的 Claude Code jsonl 版）。

用法：fi-signals-devin.py <transcript.json>          印上次 /fi 之後的訊號清單
      fi-signals-devin.py --ack <transcript.json>    標記已處理到目前 step 數（/fi 寫完才呼叫）

Devin 逐字稿：~/.local/share/devin/cli/transcripts/<codename>.json，單一 JSON
物件，steps[] 每步 {step_id, timestamp, source, message, tool_calls, observation}。
  source：system / agent / user
  agent：tool_calls[{tool_call_id, function_name, arguments:{command|file_path|…}}]
        observation {results:[{source_call_id, content}]}，exec 輸出結尾帶 "Exit code: N"
  user：message 純文字（<rules>、<system_guidance> 等注入以 < 開頭，照舊略過）

錯誤判定：observation 內容最後一個 "Exit code: N"≠0，或 STRONG_RE 命中（exec 以外的
工具沒有 Exit code 行）。正則與標記目錄直接共用 fi-signals.py。
退出碼：0 有訊號｜5 沒有新內容｜2 用法錯誤
"""
import importlib.util
import json
import os
import re
import sys

_spec = importlib.util.spec_from_file_location(
    'fi_signals', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fi-signals.py'))
_cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cc)

STATE = _cc.STATE
ERR_RE, STRONG_RE, FIX_RE = _cc.ERR_RE, _cc.STRONG_RE, _cc.FIX_RE
MAX, one_line = _cc.MAX, _cc.one_line
EXITCODE_RE = re.compile(r'^Exit code: (\d+)\s*$', re.M)


def main(argv):
    ack = '--ack' in argv
    args = [a for a in argv if a != '--ack']
    if len(args) != 1 or not os.path.isfile(args[0]):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    path = args[0]
    mark = os.path.join(STATE, os.path.basename(path).rsplit('.', 1)[0] + '.devin')
    steps = json.load(open(path, encoding='utf-8', errors='replace')).get('steps') or []
    try:
        start = int(open(mark).read().split()[0])
    except (OSError, ValueError, IndexError):
        start = 0
    if start > len(steps):  # 檔被換掉：從頭
        start = 0
    if ack:
        os.makedirs(STATE, exist_ok=True)
        with open(mark, 'w') as fh:
            fh.write('%d\n' % len(steps))
        return 0

    out, seen = [], set()
    for no, s in enumerate(steps[start:], start + 1):
        src = s.get('source')
        if src == 'agent':
            cmds = {}
            for tc in s.get('tool_calls') or []:
                a = tc.get('arguments') or {}
                cmds[tc.get('tool_call_id')] = (a.get('command') or a.get('file_path')
                                                or tc.get('function_name'))
            obs = s.get('observation') or {}
            for r in obs.get('results') or []:
                body = r.get('content') or ''
                codes = EXITCODE_RE.findall(body)
                # 任一非零 exit 或強訊號才算錯；正常輸出裡碰巧有 FAIL 字樣不算
                if not (any(c != '0' for c in codes) or STRONG_RE.search(body)):
                    continue
                rest = [l for l in body.splitlines() if l.strip() and not EXITCODE_RE.match(l)]
                first = next((l for l in rest if ERR_RE.search(l)), rest[0] if rest else body.strip())
                key = one_line(first, 80)
                if key in seen:
                    continue
                seen.add(key)
                out.append('L%d ERR %s ⇒ %s' % (no, one_line(cmds.get(r.get('source_call_id'), '?'), 120),
                                                one_line(first, 160)))
        elif src == 'user':
            said = (s.get('message') or '').strip()
            # 注入區塊（<rules>、<page_content_ref>、skill 本文）不是使用者親口說的
            if not said or said.startswith('<'):
                continue
            if FIX_RE.search(said) and said not in seen:
                seen.add(said)
                out.append('L%d USER %s' % (no, one_line(said, 160)))

    if not out:
        print('fi-signals: 上次 /fi 後沒有新訊號（step %d→%d）' % (start, len(steps)))
        return 5
    if len(out) > MAX:
        print('（只列最後 %d／%d 條）' % (MAX, len(out)))
        out = out[-MAX:]
    print('\n'.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
