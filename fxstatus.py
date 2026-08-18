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
import re
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


def zshenv_val(key):
    try:
        for line in Path(os.path.expanduser("~/.zshenv")).read_text(encoding="utf-8").splitlines():
            m = re.match(rf"^export\s+{key}=(.+)$", line.strip())
            if m:
                return m.group(1).strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def resolve_dirs():
    fixdir = os.environ.get("FIXINDEX_DIR") or zshenv_val("FIXINDEX_DIR")
    index = os.environ.get("FIXINDEX_INDEX") or zshenv_val("FIXINDEX_INDEX")
    fixdir = fixdir or str(Path.cwd() / "fixes")
    index = index or str(Path.cwd() / "FIX-INDEX.md")
    return Path(os.path.expanduser(fixdir)), Path(os.path.expanduser(index))


def git_state(fixdir):
    """回傳 (ok, dict) — ok=False 代表非 git repo（error）。"""
    rc, top, _ = run(["git", "-C", str(fixdir), "rev-parse", "--show-toplevel"])
    if rc != 0 or not top:
        return False, {"error": "not-a-git-repo"}
    s = {"root": top, "branch": None, "ahead": 0, "behind": 0, "upstream": False,
         "detached": False, "dirty_files": 0, "errors": [], "warnings": []}
    rc, branch, _ = run(["git", "-C", top, "symbolic-ref", "--short", "-q", "HEAD"])
    if rc != 0 or not branch:
        s["detached"] = True
        s["warnings"].append("detached HEAD（不可查 upstream 狀態）")
        return True, s
    s["branch"] = branch
    rc, up, _ = run(["git", "-C", top, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if rc != 0 or not up:
        s["warnings"].append(f"no upstream（branch '{branch}' 無遠端追蹤）")
        return True, s
    s["upstream"] = up
    rc, ahead, _ = run(["git", "-C", top, "rev-list", "--count", "@{u}..HEAD"])
    rc2, behind, _ = run(["git", "-C", top, "rev-list", "--count", "HEAD..@{u}"])
    try:
        s["ahead"] = int(ahead or 0)
        s["behind"] = int(behind or 0)
    except ValueError:
        pass
    if s["ahead"] > 0:
        s["errors"].append(f"{s['ahead']} unpushed commit(s)（[ahead {s['ahead']}]）")
    if s["behind"] > 0:
        s["errors"].append(f"{s['behind']} remote commit(s) not pulled（[behind {s['behind']}]）")
    rc, porc, _ = run(["git", "-C", top, "status", "--porcelain"])
    s["dirty_files"] = len([l for l in porc.splitlines() if l.strip()]) if rc == 0 else 0
    if s["dirty_files"] > 0:
        s["warnings"].append(f"{s['dirty_files']} dirty file(s)（未 commit 的工作樹）")
    return True, s


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
    s = {"errors": []}
    if not fixdir.is_dir():
        return s
    for f in sorted(fixdir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m_status = re.search(r"^status:\s*(\S+)", text, re.M)
        m_sup = re.search(r"^supersedes:\s*(\S*)", text, re.M)
        m_by = re.search(r"^superseded_by:\s*(\S+)", text, re.M)
        if m_status and m_status.group(1) == "superseded":
            sup = (m_sup.group(1) if m_sup else "").strip().strip("[]'\"")
            by = (m_by.group(1) if m_by else "").strip().strip("[]'\"")
            # 被取代的 stub（空殼佔位）用 superseded_by 表達「被誰取代」——合法。
            # supersedes 語意是「本條目取代了誰」；只有兩欄都空才是真異常。
            if not sup and not by:
                s["errors"].append(f"{f.name}: status=superseded 但 supersedes 與 superseded_by 皆空")
    return s


def report(sections, json_out=False):
    errors = [e for sec in sections.values() for e in sec.get("errors", [])]
    warnings = [w for sec in sections.values() for w in sec.get("warnings", [])]
    if json_out:
        payload = {"ok": not errors, "errors": errors, "warnings": warnings, "sections": {}}
        for name, sec in sections.items():
            payload["sections"][name] = {k: v for k, v in sec.items() if k not in ("errors", "warnings")}
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if not errors else 1

    names = {"index": "① index", "sync": "② sync", "lint": "③ lint"}
    for name, sec in sections.items():
        label = names.get(name, name)
        detail = [f"{k}={v}" for k, v in sec.items()
                  if k not in ("errors", "warnings", "root") and isinstance(v, (str, int, bool))]
        if sec.get("root"):
            detail.append(f"root={sec['root']}")
        line = f"{label} : {' '.join(detail) if detail else '—'}"
        print(line)
        for e in sec.get("errors", []):
            print(f"    ERROR   {e}")
        for w in sec.get("warnings", []):
            print(f"    WARNING {w}")
    if errors:
        print(f"fixindex status: {len(errors)} error(s) — FAIL")
    else:
        print("fixindex status: OK")
    return 0 if not errors else 1


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
    git_ok, gs = git_state(fixdir)
    if not git_ok:
        gs = {**gs, "errors": ["not a git repo（狀態不可查詢）"]}
    sections["sync"] = gs
    sections["lint"] = lint_state(fixdir)

    code = report(sections, json_out=json_out)
    return code


if __name__ == "__main__":
    sys.exit(main())