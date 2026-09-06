"""冪等檢查：_merge_symptoms 重複跑不得讓引號/反斜線翻倍（0001-hermes.md 8.5MB 事故）。"""
import os, tempfile, fxauto

FM = '---\nid: 9999\ntitle: t\nsymptoms:\n  - "hermes -z 直接 \\"agent failed\\" x"\ntags: [a]\n---\n## §1 t\n'

def demo():
    d = tempfile.mkdtemp(); p = os.path.join(d, '9999-t.md')
    open(p, 'w').write(FM)
    sizes = []
    for _ in range(5):
        fxauto._merge_symptoms(p, ['new symptom'])
        sizes.append(os.path.getsize(p))
    assert len(set(sizes)) == 1, sizes          # 重跑不長大（舊版每次翻倍）
    txt = open(p).read()
    line = [l for l in txt.splitlines() if 'hermes -z' in l][0]
    assert fxauto._unq(line.split('- ', 1)[1]) == 'hermes -z 直接 "agent failed" x', line
    assert txt.count('new symptom') == 1, txt   # 去重
    fxauto._merge_symptoms(p, ['x' * 500, 'bad \\\\\\\\ item'])
    txt = open(p).read()
    assert 'xxxx' not in txt and 'bad' not in txt  # 超長／殘渣不入庫
    print('ok', os.path.getsize(p), 'bytes')

if __name__ == '__main__':
    demo()
