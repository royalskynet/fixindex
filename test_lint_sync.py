"""fxstatus.lint_state: supersede links must be symmetric; asymmetry is a warning, never an error."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fxstatus

FM = '---\nid: "{id}"\nslug: t\ntitle: t\nsymptoms: []\nstatus: {status}\n{by}supersedes: {sup}\nrelated: []\n---\n\n# {id}\n'
def w(d, id, status, sup='[]', by=''):
    (d / f'{id}-t.md').write_text(FM.format(id=id, status=status, sup=sup, by=f'superseded_by: "{by}"\n' if by else ''))

with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    w(d, '0001', 'active', sup='[0002]')                 # forward: 0002 still active
    w(d, '0002', 'active')
    w(d, '0003', 'superseded', by='0004')                # backward: 0004 does not list 0003
    w(d, '0004', 'active')
    w(d, '0005', 'superseded', sup='[0006]')             # reversed direction
    w(d, '0006', 'active')
    w(d, '0007', 'superseded', by='0008')                # clean pair
    w(d, '0008', 'active', sup='[0007]')
    r = fxstatus.lint_state(d)
    assert r['errors'] == [], r
    ws = '\n'.join(r['warnings'])
    assert '0001-t.md: supersedes 0002' in ws, ws
    assert '0003-t.md: superseded_by 0004' in ws, ws
    assert '0005-t.md: 已 superseded' in ws and '方向反寫' in ws, ws
    assert '0007' not in ws and '0008' not in ws, ws
    assert len(r['warnings']) == 3, ws
print('PASS lint sync warnings')
