import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FXAUTO = os.path.join(HERE, 'fxauto.py')
SYM = 'the quick brown fox jumps over the lazy dog again'


def _env(tmpdir):
    return dict(os.environ,
                FIXINDEX_DIR=os.path.join(tmpdir, 'fixes'),
                FIXINDEX_INDEX=os.path.join(tmpdir, 'FIX-INDEX.md'),
                FIXINDEX_NO_SYNC='1',
                FIXINDEX_NO_BLURB='1')


def _git_init(tmpdir):
    os.makedirs(os.path.join(tmpdir, 'fixes'), exist_ok=True)
    subprocess.run(['git', 'init', '-q', tmpdir], check=True)


def _run(tmpdir, stdin):
    env = _env(tmpdir)
    r = subprocess.run([sys.executable, FXAUTO, '--commit'],
                       input=stdin, capture_output=True, text=True, env=env)
    payload = None
    for line in (r.stdout or '').splitlines():
        line = line.strip()
        if line.startswith('{'):
            payload = json.loads(line)
    return r, payload


import fxauto


def test_a():
    with tempfile.TemporaryDirectory() as d:
        _git_init(d)
        first = ('SYMPTOM: %s\nROOT: R-old\nFIX: F-old\nVERIFY: V-old\nRULE: r\n' % SYM)
        r1, p1 = _run(d, first)
        assert r1.returncode == 0, r1.stderr
        assert p1 is not None
        second = ('SYMPTOM: %s\nFIX: F-new\nRULE: r\n' % SYM)
        r2, p2 = _run(d, second)
        assert r2.returncode == 0, r2.stderr
        assert p2 is not None and p2.get('dedup') is True, p2
        path = p2['created']
        sec2 = fxauto._read_entry_section(path, 2)
        sec3 = fxauto._read_entry_section(path, 3)
        sec4 = fxauto._read_entry_section(path, 4)
        assert sec2 == 'R-old', sec2
        assert 'F-old' in sec3 and 'F-new' in sec3, sec3
        assert 'V-old' in sec4, sec4
        body = open(path, encoding='utf-8').read()
        assert 'untraced' not in body, body


def test_b():
    with tempfile.TemporaryDirectory() as d:
        _git_init(d)
        first = ('SYMPTOM: %s\nROOT: R-old\nFIX: F-old\nVERIFY: V-old\nRULE: r\n' % SYM)
        r1, p1 = _run(d, first)
        assert r1.returncode == 0, r1.stderr
        second = ('SYMPTOM: %s\nROOT: R-new\nFIX: F-x\nRULE: r\n' % SYM)
        r2, p2 = _run(d, second)
        assert r2.returncode == 0, r2.stderr
        assert p2 is not None and p2.get('dedup') is True, p2
        path = p2['created']
        sec2 = fxauto._read_entry_section(path, 2)
        assert sec2 == 'R-new', sec2


def test_c():
    with tempfile.TemporaryDirectory() as d:
        _git_init(d)
        pipe = 'SYMPTOM: a totally different unique symptom about quantum flux\nFIX: F\nVERIFY: V\nRULE: r\n'
        r, p = _run(d, pipe)
        assert r.returncode == 0, r.stderr
        assert p is not None
        path = p['created']
        sec2 = fxauto._read_entry_section(path, 2)
        assert sec2 == 'untraced', sec2


if __name__ == '__main__':
    test_a()
    test_b()
    test_c()
    print('ok dedup-inherit')