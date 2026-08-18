#!/usr/bin/env bash
# fi-reminder.sh — Claude Code Stop hook（fixindex 收尾 fi 提醒 + git 同步閘門）。
# 兩件事：
#   【閘門】若本次有 git commit/push 跡象但 fixindex status 非 clean（含離線積壓
#          pending_push）→ block，物理上擋下「commit 完沒同步就宣告完成」。
#   【提醒】若非小任務（tool_use ≥ threshold）且有除錯/修復跡象、但沒呼叫
#          fixindex fi/new/auto 記入 → block 強制補記。
# 一律輸出合法單行 JSON（decision: block/allow）。
# stop_hook_active=true 表示已 block 過一輪 → 靜默放行，防無限迴圈。
# 由 Claude Code 掛在 settings.json "hooks"."Stop"。

set -u
INPUT="$(cat)"
export INPUT

python3 - <<'PYEOF'
import os, json, subprocess, re, sys

try:
    d = json.loads(os.environ['INPUT'] or '')
except Exception:
    d = {}
tp = d.get('transcript_path') or '-'
if d.get('stop_hook_active'):
    sys.exit(0)
if tp == '-' or not tp or not os.path.isfile(tp):
    sys.exit(0)

# ---- 解析 transcript JSONL：只看 Bash tool_use 的 input.command（不看 hook 自己的 reason）----
FI_RE = re.compile(r'\bfixindex\s+(fi|new|auto)\b')
GIT_RE = re.compile(r'\bgit\b[^\n;|&]*\b(commit|push)\b')
DEBUG_RE = re.compile(
    r'error|錯誤|bug|fix(ed)?|修好|修復|除錯|debug|root cause|根因|崩'
    r'|crashed?|timeout|401|fail(ed)?|stack trace|重試|troubleshoot', re.I)

fi_called = False
git_commit_seen = False
debug_evidence = False
tool_calls = 0

try:
    with open(tp, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            t = rec.get('type')
            if t == 'tool_use':
                tool_calls += 1
                if rec.get('name') == 'Bash':
                    inp = rec.get('input')
                    cmd = str(inp.get('command') or '') if isinstance(inp, dict) else ''
                    if FI_RE.search(cmd):
                        fi_called = True
                    if GIT_RE.search(cmd):
                        git_commit_seen = True
            elif t == 'assistant':
                content = rec.get('content')
                if isinstance(content, list):
                    text = ' '.join(str(c.get('text') or '') for c in content if isinstance(c, dict))
                else:
                    text = str(content or '')
                if DEBUG_RE.search(text):
                    debug_evidence = True
except Exception:
    pass


def block(reason):
    print(json.dumps({'decision': 'block', 'reason': reason}, ensure_ascii=False))
    sys.exit(0)


# ---- 閘門：有 git commit / fixindex 寫入跡象 → 事實查核 fixindex status ----
# fixindex 不可用 / status 失敗（timeout、掛掉）→ 放行，不 block（C 搭配失敗保守放行）。
if fi_called or git_commit_seen:
    p = None
    try:
        p = subprocess.run(['fixindex', 'status', '--json', '--assert-clean'],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        p = None
    if p is not None and p.returncode != 0:
        detail = 'status 非 clean'
        ahead = behind = ''
        pen = None
        try:
            j = json.loads(p.stdout)
            errs = j.get('errors') or []
            sync = (j.get('sections') or {}).get('sync') or {}
            pen = sync.get('pending_push')
            ahead = f"；ahead {sync['ahead']}" if sync.get('ahead') else ''
            behind = f"；behind {sync['behind']}" if sync.get('behind') else ''
            detail = '；'.join(str(e) for e in errs) if errs else 'status 非 clean'
            detail = detail + ahead + behind
        except Exception:
            pass
        if pen:
            sha = (pen.get('sha') or '?')[:7]
            reason = (
                'fi-reminder: 本次有 git 同步跡象，但存在離線積壓 pending push '
                f'({sha}@{pen.get("since") or "?"})。離線是允許的：本地 commit 已留，'
                'marker 已記，網路恢復後下次寫入會自動補推。'
                '本輪 block 只出一次，一句話說明「離線、稍後補推」後即可停。')
        else:
            detail = detail or 'status 非 clean'
            reason = (
                'fi-reminder: 本次有 git 同步跡象，但 fixindex status --assert-clean 非 clean'
                f"（{detail}）。補同步後再停：unpushed commit 先 `git push`；"
                '落後 remote 先 `git pull --rebase --autostash`；'
                '若確認無需同步，一句話說明後即可停。')
        block(reason)

# ---- 規模門檻：小任務不值得 fi 成本 ----
THRESHOLD = 10
if tool_calls < THRESHOLD:
    sys.exit(0)

# ---- 提醒：疑似修過 defect 但沒記 ----
if debug_evidence and not fi_called:
    block('fi-reminder: 本次疑似修過 defect，但未見 fixindex fi/new/auto 記入。'
          '補記（printf "SYMPTOM: ...\\nFIX: ..." | fixindex fi，含實測數據與無效嘗試）；'
          '若確實無 defect 可記，一句話說明後即可停。')

sys.exit(0)
PYEOF