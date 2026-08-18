#!/usr/bin/env python3
"""fixindex status — 三段健康狀態（根治「狀態不可查詢」，0171 回歸修復）。

Usage:
  fixindex status                 三段人類可讀輸出；exit 0 = 全部正常，非 0 = 有異常
  fixindex status --assert-clean  任一 error → exit 1（供 stop hook 閘門 / CI）
  fixindex status --json          單行 JSON（machine-readable，含 errors/warnings 清單）

三段：
  ① index   FIX-INDEX.md 是否比最新 fixes/*.md 新（stale → error）
  ② sync    git 狀態：ahead/behind（error）、dirty tree（warning）、
            無 upstream／detached HEAD（warning）、非 git repo（error）
  ③ lint    superseded 但 supersedes 為空（error，0452 形態）

語意：error → exit 非 0；warning → 標出但 exit 0。
"""
import json
import os
import sys
from pathlib import Path

import fxsync
import fxmeta


def zshenv_val(key):
    prefix = f"export {key}="
    try:
        for line in Path(os.path.expanduser("~/.zshenv")).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(prefix):
                return line[len(prefix):].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def resolve_dirs():
    fixdir_env = os.environ.get("FIXINDEX_DIR")
    # B2: STRICT_DIR=1 且未顯式設定 → 禁止一切回退（含 zshenv 與 cwd）
    if fxsync.strict_dir_guard(fixdir_env):
        sys.stderr.write("fixindex: STRICT_DIR: FIXINDEX_DIR 未顯式設定，拒絕回退\n")
        sys.exit(1)
    fixdir = fixdir_env or zshenv_val("FIXINDEX_DIR")
    index = os.environ.get("FIXINDEX_INDEX") or zshenv_val("FIXINDEX_INDEX")
    fixdir = fixdir or str(Path.cwd() / "fixes")
    index = index or str(Path.cwd() / "FIX-INDEX.md")
    return Path(os.path.expanduser(fixdir)), Path(os.path.expanduser(index))


def index_state(fixdir, index):
    s = {"exists": index.exists(), "stale": False, "errors": [], "warnings": []}
    if not fixdir.is_dir():
        s["errors"].append(f"fixes dir missing: {fixdir}")
        return s
    if not index.exists():
        s["errors"].append(f"FIX-INDEX.md missing: {index}（先跑 fixindex re-index）")
        return s
    newest = 0.0
    for f in fixdir.glob("[0-9][0-9][0-9][0-9]-*.md"):
        try:
            newest = max(newest, f.stat().st_mtime)
        except OSError:
            pass
    try:
        idx_mtime = index.stat().st_mtime
    except OSError:
        idx_mtime = 0.0
    if newest > idx_mtime + 1:
        s["stale"] = True
        s["errors"].append("FIX-INDEX.md stale（比最新 fixes/*.md 舊；先跑 fixindex re-index）")
    return s


def lint_state(fixdir):
    """③ lint：superseded 但 supersedes 兩欄皆空 → error（0452 形態）。
    解析統一走 fxmeta（不重造 regex；supersedes 單值/block 都吃）。"""
    s = {"errors": []}
    if not fixdir.is_dir():
        return s
    for f in sorted(fixdir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        fm, _ = fxmeta.parse_frontmatter_full(text)
        status = str(fm.get("status") or "").strip().strip('"\'')
        supersedes = fm.get("supersedes") or []
        if isinstance(supersedes, str):
            supersedes = [supersedes] if supersedes.strip() else []
        superseded_by = str(fm.get("superseded_by") or "").strip().strip('"\'')
        # 被取代的 stub（空殼佔位）用 superseded_by 表達「被誰取代」——合法。
        # supersedes 語意是「本條目取代了誰」；只有兩欄都空才是真異常。
        if status == "superseded" and not supersedes and not superseded_by:
            s["errors"].append(f"{f.name}: status=superseded 但 supersedes 與 superseded_by 皆空")
    return s


def report(sections, json_out=False, assert_clean=False):
    """三段輸出。fail = errors 或 pending_push（離線積壓）存在。
    --assert-clean：fail → exit 1（供 stop hook 閘門 / CI）。"""
    errors = [e for sec in sections.values() for e in sec.get("errors", [])]
    warnings = [w for sec in sections.values() for w in sec.get("warnings", [])]
    pending = [sec.get("pending_push") for sec in sections.values() if sec.get("pending_push")]
    fail = bool(errors) or bool(pending)
    if json_out:
        payload = {"ok": not fail, "errors": errors, "warnings": warnings, "sections": {}}
        for name, sec in sections.items():
            sec_out = {k: v for k, v in sec.items() if k not in ("errors", "warnings")}
            if "pending_push" in sec_out and sec_out["pending_push"] is None:
                sec_out["pending_push"] = None  # 保留 key，machine 端可讀為「無積壓」
            payload["sections"][name] = sec_out
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if not fail else 1

    names = {"index": "① index", "sync": "② sync", "lint": "③ lint"}
    for name, sec in sections.items():
        label = names.get(name, name)
        detail = [f"{k}={v}" for k, v in sec.items()
                  if k not in ("errors", "warnings", "root", "pending_push")
                  and isinstance(v, (str, int, bool))]
        if sec.get("root"):
            detail.append(f"root={sec['root']}")
        line = f"{label} : {' '.join(detail) if detail else '—'}"
        print(line)
        for e in sec.get("errors", []):
            print(f"    ERROR   {e}")
        for w in sec.get("warnings", []):
            print(f"    WARNING {w}")
        pp = sec.get("pending_push")
        if pp:
            sha = (pp.get("sha") or "?")[:7]
            print(f"    PENDING 離線積壓 push {sha}@{pp.get('since') or '?'}（網路恢復後下次寫入自動補推）")
    if fail:
        print(f"fixindex status: {len(errors)} error(s) — FAIL")
    else:
        print("fixindex status: OK")
    return 0 if not fail else 1


def main():
    args = [a for a in sys.argv[1:] if a.startswith("-")]
    assert_clean = "--assert-clean" in args
    json_out = "--json" in args
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0

    fixdir, index = resolve_dirs()
    sections = {}
    sections["index"] = index_state(fixdir, index)
    sections["sync"] = fxsync.state(fixdir)
    sections["lint"] = lint_state(fixdir)

    code = report(sections, json_out=json_out, assert_clean=assert_clean)
    return code


if __name__ == "__main__":
    sys.exit(main())