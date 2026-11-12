#!/usr/bin/env python3
"""fi_pipeline — fi-deep.sh 的 pipeline 模式執行器。

用法：fi_pipeline.py <W>
W 是 fi-deep.sh 的工作目錄，內有 part.*.txt。只用 Python 標準函式庫。

退出碼：0 成功｜2 用法錯誤｜3 抽候選或裁決失敗（不寫任何條目）｜4 fixindex fi 失敗
"""
import glob
import json
import os
import shlex
import subprocess
import sys

DEFAULT_ASK = 'bash ' + os.path.expanduser('~/.claude/skills/ds-claude/scripts/ds-run.sh')


def eprint(*args):
    print(*args, file=sys.stderr)


def run_ask(w, question):
    raw = os.environ.get('FI_ASK_CMD') or DEFAULT_ASK
    argv = shlex.split(os.path.expanduser(raw)) + [w, '--ask', question]
    return subprocess.run(argv, capture_output=True, text=True)


def run_fixindex(args, stdin=None):
    return subprocess.run(['fixindex'] + args, input=stdin, capture_output=True, text=True)


def parse_hits(out):
    try:
        data = json.loads(out)
    except Exception:
        return {}
    items = []
    if isinstance(data, dict):
        if isinstance(data.get('queries'), list):
            items = data['queries']
        elif 'query' in data:
            items = [data]
    mapping = {}
    for item in items:
        if isinstance(item, dict) and 'query' in item:
            mapping[item['query']] = item.get('hits') or []
    return mapping


def last_result(out):
    for line in reversed((out or '').splitlines()):
        s = line.strip()
        if not s.startswith('{'):
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict) and ('created' in obj or 'appended' in obj):
            return obj
    return None


def number_from_path(path):
    return os.path.basename(str(path)).split('-', 1)[0]


def as_value(value):
    if value is None:
        return ''
    return str(value)


def main():
    if len(sys.argv) < 2:
        eprint('用法：fi_pipeline.py <W>')
        return 2
    w = sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    prompts = os.path.join(here, 'fi-prompts')
    notes_path = os.path.join(w, 'task', 'notes.md')
    os.makedirs(os.path.join(w, 'task'), exist_ok=True)

    def ask(question):
        try:
            os.remove(notes_path)
        except FileNotFoundError:
            pass
        proc = run_ask(w, question)
        if proc.returncode != 0:
            eprint('fi_pipeline: LLM 指令失敗（exit %d）' % proc.returncode)
            detail = ((proc.stdout or '') + (proc.stderr or '')).strip()
            if detail:
                eprint(detail)
            return None
        try:
            with open(notes_path, encoding='utf-8') as fh:
                text = fh.read()
        except FileNotFoundError:
            eprint('fi_pipeline: 找不到 %s' % notes_path)
            return None
        if not text.strip():
            eprint('fi_pipeline: %s 是空的' % notes_path)
            return None
        return text

    # 1. 抽候選
    with open(os.path.join(prompts, 'extract.md'), encoding='utf-8') as fh:
        extract_question = fh.read()
    text = ask(extract_question)
    if text is None:
        return 3

    candidates = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith('{'):
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if 'kind' not in obj or 'quote' not in obj or 'fields' not in obj:
            continue
        obj['i'] = len(candidates)
        candidates.append(obj)

    part_texts = []
    for path in sorted(glob.glob(os.path.join(w, 'part.*.txt'))):
        with open(path, encoding='utf-8') as fh:
            part_texts.append(fh.read())

    # 2. 機械過濾
    passed = []
    skipped = []
    for cand in candidates:
        quote = as_value(cand.get('quote'))
        core = as_value(cand.get('core'))
        fields = cand.get('fields') if isinstance(cand.get('fields'), dict) else {}
        reason = None
        if len(''.join(quote.split())) < 12:
            reason = '引用太短'
        elif not any(quote in part for part in part_texts):
            reason = '引用不在逐字稿'
        elif not as_value(fields.get('RULE')).strip():
            reason = '缺 RULE'
        if reason:
            skipped.append((cand['i'], core, reason))
        else:
            passed.append(cand)

    created = []
    appended = []
    failed = False

    if passed:
        # 3. 批次查重
        queries = []
        qmap = {}
        for cand in passed:
            q = as_value(cand.get('query') or cand.get('core') or '')
            queries.append(q)
            qmap[cand['i']] = q
        queries_path = os.path.join(w, 'queries.txt')
        with open(queries_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(queries) + '\n')

        find_proc = run_fixindex(['find', '--queries-file', queries_path, '--json', '--limit', '5'])
        if find_proc.returncode != 0:
            eprint('fi_pipeline: fixindex find 失敗')
            eprint((find_proc.stdout or '') + (find_proc.stderr or ''))
            return 3
        find_hits = parse_hits(find_proc.stdout)

        ins_proc = run_fixindex(['insights', '--queries-file', queries_path, '--json', '--limit', '5'])
        if ins_proc.returncode != 0:
            eprint('fi_pipeline: fixindex insights 失敗')
            eprint((ins_proc.stdout or '') + (ins_proc.stderr or ''))
            return 3
        ins_hits = parse_hits(ins_proc.stdout)

        for cand in passed:
            q = qmap[cand['i']]
            cand['hits'] = list(find_hits.get(q, [])) + list(ins_hits.get(q, []))

        # 4. 裁決
        adjudicate_path = os.path.join(w, 'adjudicate.json')
        payload = []
        for cand in passed:
            payload.append({
                'i': cand['i'],
                'kind': cand.get('kind'),
                'core': cand.get('core'),
                'quote': cand.get('quote'),
                'fields': cand.get('fields'),
                'hits': cand.get('hits', []),
            })
        with open(adjudicate_path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
        with open(os.path.join(prompts, 'adjudicate.md'), encoding='utf-8') as fh:
            adjudicate_question = fh.read().replace('{INPUT}', os.path.abspath(adjudicate_path))
        answer = ask(adjudicate_question)
        if answer is None:
            return 3

        decisions = {}
        for line in answer.splitlines():
            s = line.strip()
            if not s.startswith('{'):
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if not isinstance(obj, dict) or 'i' not in obj or 'action' not in obj:
                continue
            try:
                decisions[int(obj['i'])] = obj  # LLM 常把 i 寫成字串 "0"
            except (TypeError, ValueError):
                continue

        writes = []
        for cand in passed:
            i = cand['i']
            core = as_value(cand.get('core'))
            decision = decisions.get(i)
            if decision is None:
                skipped.append((i, core, '裁決未提及'))
                continue
            if decision.get('action') == 'write':
                fields = cand.get('fields') if isinstance(cand.get('fields'), dict) else {}
                if isinstance(decision.get('fields'), dict):
                    fields = decision['fields']
                writes.append((i, cand, fields))
            else:
                skipped.append((i, core, as_value(decision.get('reason')) or '略過'))

        # 5. 寫入
        for i, cand, fields in sorted(writes, key=lambda item: item[0]):
            core = as_value(cand.get('core'))
            quote = as_value(cand.get('quote'))
            fields = dict(fields)
            if cand.get('kind') == 'insight':
                order = ['CONTEXT', 'INSIGHT', 'IMPLICATION', 'QUERIES', 'RULE']
                quote_key = 'CONTEXT'
            else:
                order = ['SYMPTOM', 'ROOT', 'FIX', 'VERIFY', 'RULE']
                quote_key = 'SYMPTOM'

            value = as_value(fields.get(quote_key))
            if quote not in value:
                value = (value + ' 原文：' + quote) if value else (' 原文：' + quote)
            fields[quote_key] = value

            lines = []
            for key in order:
                raw = as_value(fields.get(key)).replace('\r', ' ').replace('\n', ' ')
                if not raw.strip():
                    continue
                lines.append('%s: %s' % (key, raw))
            stdin_text = '\n'.join(lines) + ('\n' if lines else '')

            proc = run_fixindex(['fi'], stdin=stdin_text)
            if proc.returncode != 0:
                eprint(((proc.stdout or '') + (proc.stderr or '')).rstrip())
                failed = True
                break
            result = last_result(proc.stdout)
            if result is None:
                eprint('fi_pipeline: fixindex fi 輸出無法解析')
                eprint((proc.stdout or '').rstrip())
                failed = True
                break
            if result.get('created'):
                created.append((number_from_path(result['created']), core, quote))
            elif result.get('appended'):
                appended.append((number_from_path(result['appended']), core, quote))
            else:
                eprint('fi_pipeline: fixindex fi 輸出缺少 created／appended')
                eprint((proc.stdout or '').rstrip())
                failed = True
                break

    # 6. 報告
    skipped.sort(key=lambda item: item[0])
    report = ['## 新增']
    if created:
        for number, core, quote in created:
            report.append('- %s %s' % (number, core))
            report.append('  原文：%s' % quote)
    else:
        report.append('- 無')
    report.append('## 補充既有')
    for number, core, quote in appended:
        report.append('- %s %s' % (number, core))
        report.append('  原文：%s' % quote)
    report.append('## 略過')
    for _i, core, reason in skipped:
        report.append('- %s — %s' % (core, reason))
    report.append('## status')

    status_proc = run_fixindex(['status', '--json', '--assert-clean'])
    body = '\n'.join(report) + '\n' + (status_proc.stdout or '')
    if not body.endswith('\n'):
        body += '\n'

    report_path = os.path.join(w, 'report.md')
    with open(report_path, 'w', encoding='utf-8') as fh:
        fh.write(body)

    print(report_path)
    return 4 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
