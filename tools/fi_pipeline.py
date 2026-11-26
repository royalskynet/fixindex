#!/usr/bin/env python3
"""fi_pipeline — fi-deep.sh 的 pipeline 模式執行器。

用法：fi_pipeline.py <W>
W 是 fi-deep.sh 的工作目錄，內有 part.*.txt。只用 Python 標準函式庫。

退出碼：0 成功｜2 用法錯誤｜3 抽候選或裁決失敗（不寫任何條目）｜4 fixindex fi 失敗｜6 超過 FI_DEADLINE_AT（不寫任何條目）
"""
import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DEFAULT_ASK = 'bash ' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fi-ask.sh')


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
    deadline = float(os.environ.get('FI_DEADLINE_AT') or 0)
    # LLM 段提早收手，留時間給寫入（每條約 8 秒，含 pull／push）與 fi-run 的驗收
    llm_deadline = deadline - float(os.environ.get('FI_RESERVE') or 15) if deadline else 0
    if llm_deadline:
        os.environ['FI_DEADLINE_AT'] = str(int(llm_deadline))  # fi-ask 照這個收手

    def late():
        return llm_deadline and time.time() >= llm_deadline

    def ask(name, src, question):
        # 每次呼叫一個子目錄、只放要讀的那個檔：可平行，且 fi-ask 把子目錄頂層檔全附進訊息
        d = os.path.join(w, 'ask.' + name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(os.path.join(d, 'task'))
        shutil.copy(src, d)
        notes_path = os.path.join(d, 'task', 'notes.md')
        proc = run_ask(d, question)
        if proc.returncode != 0:
            eprint('fi_pipeline: LLM 指令失敗（%s，exit %d）' % (name, proc.returncode))
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

    part_paths = sorted(glob.glob(os.path.join(w, 'part.*.txt')))
    part_texts = []
    for path in part_paths:
        with open(path, encoding='utf-8') as fh:
            part_texts.append(fh.read())

    # 1. 抽候選：每塊各問一次。一次塞整個 session 時 flash 只讀前段，後段的經驗會漏掉
    with open(os.path.join(prompts, 'extract.md'), encoding='utf-8') as fh:
        extract_template = fh.read()
    candidates = []
    # 各塊平行抽；結果照塊序收，候選編號穩定
    with ThreadPoolExecutor(max_workers=max(1, len(part_paths))) as pool:
        answers = list(pool.map(
            lambda p: ask('extract.' + os.path.basename(p), p,
                          extract_template.replace('{PART}', os.path.basename(p))),
            part_paths))
    if late():
        eprint('fi_pipeline: 抽候選超過時限')
        return 6
    for text in answers:
        if text is None:
            return 3
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
    timed_out = False

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

        # find 每支程序光載入索引約 5 秒、每條 query 再約 1 秒：超過 4 條就切成最多 4 組平行跑，和 insights 同時
        size = max(3, -(-len(queries) // 4))
        groups = [queries[k:k + size] for k in range(0, len(queries), size)]
        group_paths = []
        for n, group in enumerate(groups):
            path = queries_path if len(groups) == 1 else os.path.join(w, 'queries.%d.txt' % n)
            if len(groups) > 1:
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write('\n'.join(group) + '\n')
            group_paths.append(path)
        with ThreadPoolExecutor(max_workers=len(group_paths) + 1) as pool:
            ins_f = pool.submit(run_fixindex, ['insights', '--queries-file', queries_path, '--json', '--limit', '5'])
            find_fs = [pool.submit(run_fixindex, ['find', '--queries-file', p, '--json', '--limit', '5'])
                       for p in group_paths]
            find_procs, ins_proc = [f.result() for f in find_fs], ins_f.result()
        find_hits = {}
        for find_proc in find_procs:
            if find_proc.returncode != 0:
                eprint('fi_pipeline: fixindex find 失敗')
                eprint((find_proc.stdout or '') + (find_proc.stderr or ''))
                return 3
            find_hits.update(parse_hits(find_proc.stdout))

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
            adjudicate_question = fh.read().replace('{INPUT}', 'adjudicate.json')
        answer = ask('adjudicate', adjudicate_path, adjudicate_question)
        if answer is None:
            return 6 if late() else 3
        if late():
            eprint('fi_pipeline: 裁決超過時限，不寫入')
            return 6

        def parse_decisions(text):
            parsed = {}
            for line in (text or '').splitlines():
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
                    parsed[int(obj['i'])] = obj  # LLM 常把 i 寫成字串 "0"
                except (TypeError, ValueError):
                    continue
            return parsed

        decisions = parse_decisions(answer)
        expected_ids = [cand['i'] for cand in passed]
        missing = [i for i in expected_ids if i not in decisions]
        if missing:
            retry_question = adjudicate_question + (
                '\n你上次輸出漏了候選 i：%s。這次必須對輸入陣列裡每個 i 各輸出一行 JSON；'
                '少任何一個 i 都視為裁決失敗。' % ','.join(map(str, missing))
            )
            retry = ask('adjudicate-retry', adjudicate_path, retry_question)
            if retry is None:
                eprint('fi_pipeline: 裁決漏 id，重問失敗')
                return 6 if late() else 3
            decisions = parse_decisions(retry)
            missing = [i for i in expected_ids if i not in decisions]
        if missing:
            eprint('fi_pipeline: 裁決仍漏候選 id：%s；fail-closed 不寫入' % ','.join(map(str, missing)))
            return 3

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
            if deadline and time.time() + 10 > deadline:
                # 已寫的保留；標記不前移，下次 /fi 重抽時查重會認出已寫的
                eprint('fi_pipeline: 寫入前剩不到 10 秒，停止寫入')
                timed_out = True
                break
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

    if not failed and not timed_out:
        commit_mark(w)
    print(report_path)
    return 4 if failed else 6 if timed_out else 0


def commit_mark(w):
    """fi-deep.sh 寫的 <W>/mark＝「標記檔<TAB>已處理行數」；全部寫完才前移，下次 /fi 只掃新增部分。"""
    try:
        with open(os.path.join(w, 'mark'), encoding='utf-8') as fh:
            path, lines = fh.read().strip().split('\t')
    except (FileNotFoundError, ValueError):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(lines + '\n')


if __name__ == '__main__':
    sys.exit(main())
