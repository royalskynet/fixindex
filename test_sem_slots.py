#!/usr/bin/env python3
"""語意層併發上限＋條目向量快取（2026-10-22 整機當機）。

子代理併發跑 fixindex，每支載模型 ~2GB，swap 衝到 27GB、WindowServer 卡死。
名額滿時必須退回 BM25 而不是再載一份模型；快取命中時不得重算全部條目。
"""
import os, subprocess, sys, tempfile, time

tmp = tempfile.mkdtemp()
os.environ['FIXINDEX_CACHE_DIR'] = tmp
os.environ['FIXINDEX_SEM_SLOTS'] = '2'
import fxsearch


def test_slots_full_falls_back():
    holder = ("import fcntl,os,sys,time\n"
              "fds=[os.open(os.path.join(sys.argv[1],f'sem-slot-{i}'),os.O_CREAT|os.O_RDWR) for i in range(2)]\n"
              "[fcntl.flock(f,fcntl.LOCK_EX) for f in fds]\n"
              "print('held',flush=True); time.sleep(30)\n")
    p = subprocess.Popen([sys.executable, '-c', holder, tmp], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == 'held'
        fxsearch._SEM_CACHE = None
        assert fxsearch._semantic_layer() is None, 'slots full but semantic layer still loaded'
        assert 'model2vec' not in sys.modules, 'model imported despite no slot'
    finally:
        p.kill()


def test_entry_cache_skips_reencode():
    import numpy as np

    class Fake:
        calls = 0
        def encode(self, xs, show_progress_bar=False):
            Fake.calls += len(xs)
            return np.ones((len(xs), 4), dtype=np.float32)

    raws = ['a', 'b', 'c']
    m = Fake()
    fxsearch._entry_matrix(m, np, raws)
    first = Fake.calls
    fxsearch._entry_matrix(m, np, raws)
    assert Fake.calls == first, 'cache hit still re-encoded entries'
    fxsearch._entry_matrix(m, np, raws + ['d'])
    assert Fake.calls == first + 4, 'changed entries must invalidate cache'


if __name__ == '__main__':
    test_slots_full_falls_back()
    test_entry_cache_skips_reencode()
    print('PASS test_sem_slots')
