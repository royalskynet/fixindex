"""Superseded files must rank below the live entry that absorbed them and show [X]."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FM = "---\nid: \"{id}\"\nslug: t\ntitle: heredoc temp file cwd probe\nsymptoms:\n  - 'heredoc temp file cwd probe'\nstatus: {status}\nsupersedes: {sup}\nrelated: []\n---\n\n# {id} x\n\n## §1 Symptom\n\nheredoc temp file cwd probe fails in write-deny cwd\n"

def run(fixdir, *extra):
    env = dict(os.environ, FIXINDEX_DIR=fixdir, FIXINDEX_SEMANTIC='0')
    return subprocess.run([sys.executable, os.path.join(HERE, 'fxsearch.py'), 'heredoc temp file cwd probe', *extra],
                          capture_output=True, text=True, env=env)

with tempfile.TemporaryDirectory() as d:
    # no link: superseded still listed, half score, [X]
    open(os.path.join(d, '0001-old.md'), 'w').write(FM.format(id='0001', status='superseded', sup='[]'))
    open(os.path.join(d, '0002-live.md'), 'w').write(FM.format(id='0002', status='active', sup='[]'))
    hits = json.loads(run(d, '--json').stdout)['hits']
    keys = [h['key'][:4] for h in hits]
    assert keys == ['0002', '0001'], keys
    assert hits[1]['score'] <= hits[0]['score'] * 0.5 + 1e-6, hits
    assert hits[1]['trust_state'] == 'superseded', hits[1]
    assert '0001#1   [X]' in run(d).stdout
    # linked: absorber present -> superseded hidden
    open(os.path.join(d, '0002-live.md'), 'w').write(FM.format(id='0002', status='active', sup='[0001]'))
    keys = [h['key'][:4] for h in json.loads(run(d, '--json').stdout)['hits']]
    assert keys == ['0002'], keys
print('PASS superseded rank/badge')
