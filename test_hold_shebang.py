#!/usr/bin/env python3
"""fix 9983: `fxsync.py hold -- <fixindex>` must run the script once, on any OS.

Three Windows failures behind one symptom (every write command dead):
1. `fixindex` is an extensionless bash script; CreateProcess can't exec it ->
   WinError 193 before touching data.
2. The path reached bash with backslashes, so `${self%/*}` in the script lost
   its directory and sibling files (fxauto.py) weren't found.
3. Without fcntl the lock is never "got", the child didn't get the re-entry
   marker, and `fixindex` wrapped itself in `hold` again -> unbounded fork chain
   (1355 processes in the incident).

ponytail: asserts the observable outcome (the script runs, sees the re-entry
marker, and its exit code comes back through hold), not how it is achieved.
The fake script exits 9 where the real one would re-wrap.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fxsync  # noqa: E402

FAKE = ('#!/usr/bin/env bash\n'
        '[ -f "${BASH_SOURCE[0]%/*}/fake-fixindex" ] || exit 8\n'  # same lookup fixindex uses for fxauto.py
        '[ -n "${FIXINDEX_REPO_LOCK_HELD:-}" ] || exit 9\n'
        'exit 7\n')


def run_case(label, d):
    script = os.path.join(d, "fake-fixindex")
    with open(script, "w", newline="\n") as f:
        f.write(FAKE)
    os.chmod(script, 0o755)
    env_backup = os.environ.pop(fxsync.LOCK_HELD_ENV, None)
    try:
        rc = fxsync.hold(d, [script])
    except OSError as e:
        print(f"FAIL [{label}]: hold could not spawn shebang script: {e}")
        return False
    finally:
        if env_backup is not None:
            os.environ[fxsync.LOCK_HELD_ENV] = env_backup
    if rc == 8:
        print(f"FAIL [{label}]: script can't locate its own directory (backslash path into bash)")
        return False
    if rc == 9:
        print(f"FAIL [{label}]: child got no re-entry marker (real fixindex would re-wrap forever)")
        return False
    if rc != 7:
        print(f"FAIL [{label}]: expected script exit 7 through hold, got {rc}")
        return False
    print(f"ok [{label}]")
    return True


def main():
    ok = True
    with tempfile.TemporaryDirectory() as d:  # not a repo -> lock-free path
        ok &= run_case("no repo", d)
    with tempfile.TemporaryDirectory() as d:  # repo -> lock path (got=False without fcntl)
        subprocess.run(["git", "init", "-q", d], check=True)
        ok &= run_case("repo", d)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
