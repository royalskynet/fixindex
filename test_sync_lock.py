#!/usr/bin/env python3
"""fix 9221/9439: parallel read-only queries must not corrupt .git/FETCH_HEAD.

Each read-only fixindex command runs a soft `git pull --rebase`; unserialised,
overlapping pulls left duplicated for-merge lines in FETCH_HEAD and git then
reported "Cannot rebase onto multiple branches" on a correctly configured repo.

ponytail: asserts the observable symptom (that stderr line, and a FETCH_HEAD
with more than one mergeable head), not the lock's internals.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fxsync  # noqa: E402

BAD = "Cannot rebase onto multiple branches"


def mergeable_heads(root):
    path = os.path.join(root, ".git", "FETCH_HEAD")
    if not os.path.isfile(path):
        return 0
    with open(path) as f:
        return sum(1 for ln in f if ln.strip() and "not-for-merge" not in ln)


def main():
    root = fxsync.repo_root(os.environ.get("FIXINDEX_DIR") or
                            os.path.expanduser("~/dev/fix-store"))
    if not root or not fxsync.has_upstream(root):
        print("skip: no git repo with upstream to exercise")
        return 0

    # Lock is held -> a second attempt must not get it (and must not hang).
    with fxsync._repo_lock(root) as outer:
        if not outer:
            print("skip: flock unavailable here")
            return 0
        with fxsync._repo_lock(root, timeout=1) as inner:
            assert inner is False, "reentrant acquire must fail, not double-enter"
    with fxsync._repo_lock(root, timeout=1) as again:
        assert again is True, "lock not released"

    procs = [subprocess.Popen(["fixindex", "find", "sync"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              text=True) for _ in range(6)]
    errs = [p.communicate()[1] or "" for p in procs]
    hits = [e for e in errs if BAD in e]
    assert not hits, f"{len(hits)}/6 parallel reads hit the race:\n{hits[0][:300]}"
    heads = mergeable_heads(root)
    assert heads <= 1, f".git/FETCH_HEAD left {heads} mergeable heads"
    print(f"ok: 6 parallel reads clean, FETCH_HEAD mergeable heads={heads}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
