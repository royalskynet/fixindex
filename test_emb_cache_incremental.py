#!/usr/bin/env python3
"""嵌入快取逐條失效：新增一條只重算那一條，不是整庫。

舊版拿全庫內容的 sha 當單一 key，/fi 一輪寫十幾條就重算十幾次全庫。
這個測試在舊版會 fail（第二次 encode 會收到全部 4 條）。
"""
import os, sys, tempfile, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import numpy as np
except ImportError:
    print("SKIP: numpy 未安裝（語意層是選配）")
    sys.exit(0)

import fxsearch

DIM = 8


class FakeModel:
    """deterministic encode；記錄每次收到幾條。"""
    def __init__(self):
        self.calls = []

    def encode(self, texts, **kw):
        self.calls.append(list(texts))
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            h = hashlib.sha1(t.encode()).digest()
            out[i] = np.frombuffer(h[:DIM], dtype=np.uint8).astype(np.float32)
        return out


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        os.environ['FIXINDEX_CACHE_DIR'] = d
        m = FakeModel()
        raws = ['alpha entry', 'beta entry', 'gamma entry']

        mat1 = fxsearch._entry_matrix(m, np, raws)
        if len(m.calls) != 1 or len(m.calls[0]) != 3:
            fails.append(f"首次應 encode 全部 3 條，實收 {m.calls}")

        # 全部命中：不應再 encode
        m.calls.clear()
        mat2 = fxsearch._entry_matrix(m, np, raws)
        if m.calls:
            fails.append(f"內容未變不該重算，實收 {m.calls}")
        if not np.allclose(mat1, mat2):
            fails.append("快取命中時向量與首次不一致")

        # 新增一條：只重算那一條
        m.calls.clear()
        raws3 = raws + ['delta entry']
        mat3 = fxsearch._entry_matrix(m, np, raws3)
        encoded = [t for c in m.calls for t in c]
        if encoded != ['delta entry']:
            fails.append(f"新增一條只該 encode 那一條，實收 {encoded}")
        if not np.allclose(mat3[:3], mat1):
            fails.append("既有條目的向量在新增後被改動")
        if mat3.shape[0] != 4:
            fails.append(f"矩陣列數應等於條目數 4，實得 {mat3.shape[0]}")

        # 改一條內容：只重算那一條
        m.calls.clear()
        raws4 = ['alpha entry', 'beta CHANGED', 'gamma entry', 'delta entry']
        fxsearch._entry_matrix(m, np, raws4)
        encoded = [t for c in m.calls for t in c]
        if encoded != ['beta CHANGED']:
            fails.append(f"改一條只該 encode 那一條，實收 {encoded}")

    if fails:
        for f in fails:
            print("FAIL:", f)
        sys.exit(1)
    print("PASS test_emb_cache_incremental")


if __name__ == '__main__':
    main()
