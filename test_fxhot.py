"""fxhot: >=3 distinct sessions in window promotes; fewer, stale, or unknown ids stay out."""
import json, os, subprocess, sys, tempfile, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
fresh = (now - dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
stale = (now - dt.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.000Z')

with tempfile.TemporaryDirectory() as d:
    log, pit = os.path.join(d, 'r.jsonl'), os.path.join(d, 'p.tsv')
    rows = [{'ts': fresh, 'session': s, 'layer': 'pitfall', 'ids': ['A']} for s in 'abc']      # 3 sessions -> in
    rows += [{'ts': fresh, 'session': 'a', 'layer': 'pitfall', 'ids': ['B']}] * 5               # 1 session x5 -> out
    rows += [{'ts': stale, 'session': s, 'layer': 'pitfall', 'ids': ['C']} for s in 'abcd']     # stale -> out
    rows += [{'ts': fresh, 'session': s, 'layer': 'bm25', 'ids': ['D']} for s in 'abcd']        # not pitfall -> out
    rows += [{'ts': fresh, 'session': s, 'layer': 'pitfall', 'ids': ['Z']} for s in 'abcd']     # not in tsv -> out
    open(log, 'w').write('\n'.join(map(json.dumps, rows)) + '\nnot json\n')
    open(pit, 'w').write('# hdr\nA\tBash\tx\tdeny\tadvice-A\nB\tBash\tx\twarn\tadvice-B\n'
                         'C\tBash\tx\twarn\tadvice-C\nD\tBash\tx\twarn\tadvice-D\n')
    env = dict(os.environ, FIXINDEX_RECALL_LOG=log, FIXINDEX_PITFALLS=pit)
    out = subprocess.run([sys.executable, os.path.join(HERE, 'fxhot.py')], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    assert '[fix A] 必擋·3s  advice-A' in out.stdout, out.stdout
    for bad in ('fix B', 'fix C', 'fix D', 'fix Z'):
        assert bad not in out.stdout, (bad, out.stdout)
    # missing log -> fail-open, empty output
    env['FIXINDEX_RECALL_LOG'] = os.path.join(d, 'none')
    out = subprocess.run([sys.executable, os.path.join(HERE, 'fxhot.py')], capture_output=True, text=True, env=env)
    assert out.returncode == 0 and out.stdout == '', out
print('PASS fxhot promote/decay')
