# Fix Logs Directory

This repo ships **only the CLI**. Your fix logs live in your own (usually private) checkout.

By default `fixindex` falls back to `./fixes/` relative to the current working
directory. That default is fine for a quick look, but it is a trap for writes:
run `fixindex new` from the wrong directory and the entry lands in a second,
silent runbook that `find` will never search from anywhere else. Write commands
print a warning when `FIXINDEX_DIR` is unset — set it once and forget it:

```bash
export FIXINDEX_DIR="$HOME/notes/runbook/fixes"
export FIXINDEX_INDEX="$HOME/notes/runbook/FIX-INDEX.md"
```

Put those in your shell profile. If an agent or daemon runs `fixindex` on your
behalf, make sure **its** environment has them too — background services often
don't read your interactive shell's rc files, which is exactly how a stray
runbook gets created.

`fixes/[0-9]*.md` is gitignored here so personal entries can never be committed
to the public repo by accident. Only `.template.md` and this README are tracked.
