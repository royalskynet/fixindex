# FIX-INDEX

Personal bug runbook — symptom → fix lookup, adr-tools style.

## Quick start

```bash
fixindex find "<symptom keyword>"   # match frontmatter `symptoms:` across fix files
fixindex show 0001                  # cat fixes/0001-*.md
fixindex list                       # all entries
fixindex grep "<keyword>"           # full-text ripgrep including bodies
fixindex new <slug>                 # scaffold next-numbered fix file
fixindex re-index                   # regenerate the directory table below (idempotent)
fixindex supersede <old> <new>      # mark old superseded by new
```

Each fix lives in `fixes/NNNN-<slug>.md` with a YAML frontmatter (`id / slug / title / tags / symptoms[] / status / supersedes[] / related[]`) and one or more `## §N {title}` sections shaped as **Symptom / Root cause / Fix / Verify / Retrospective** (Retrospective optional — record only when there is a lesson worth carrying forward).

## Directory

<!-- fixindex:table:start -->
| ID | Slug | Title | Tags |
|----|------|-------|------|
| 0001 | coco-monday-weekly-schedule-night-shift-notify | TODO |  |
| 0002 | omniroute-fts-tail-nim-fallback | OmniRoute FTS combo tail NIM fallback | omniroute, fts, combo, nvidia-nim, launchd, timeout, readiness |
| 0003 | heath-bot-silent-pkill-missed-rescue | Heath bot 靜默 20 天 — pkill 廣域 pattern 誤殺後漏救 |  |
| 0004 | fts-dispatch-not-in-slash-menu | "fts codex `/dispatch` 不出現在斜線選單——prompt 放在 Happy 不掃的目錄" | "codex-fts", "happy", "dispatch", "skill-system" |
| 0005 | codex-novelvault-agents-integration | TODO |  |
| 0006 | mini-power-failure-vdd-boost-uvlo | Mini 突然斷電重啟 — 供電壓降 UVLO |  |
| 0007 | cheeragent-hook-tailread-pregen | "cheeragent hook 效能優化 — tail-read + background pregen" | "cheeragent", "hook", "performance", "node" |
| 0008 | --help | TODO |  |
| 0009 | fts-codex-timeout-prefill-bloat | "FTS Codex 停止：header timeout（協定層）+ 75k tool schema（臃腫層）+ 自評放水（判定層）" | fts, codex, omniroute, strip-proxy, timeout, tool_search, hooks, hook-trust, claude-mem, mem0, skills |
| 0010 | fts-harness-continue-needed-loop | FTS harness poll 無限 continue-needed、監控空轉、context 無人守門 | fts, harness, codex, launchd, strip-proxy, stop-hook, poll |
| 0011 | fts-harness-layer-stall-coverage | FTS session 宣告下一步後停擺、HL 三層全數空轉 | fts, harness, codex, stop-hook, goals, poll, launchd, bash |
| 0012 | fts-harness-selfheal-online | FTS harness 自癒閉環上線 — 假警報止血、空轉 turn 偵測、doctor/layer1.8 啟用 | fts, harness, launchd, telegram, acceptance-gate, opencode, codex, self-heal |
| 0013 | novelvault-migo-cleanup | TODO |  |
| 0014 | opencode-dispatch-protocol | opencode 派工協定 — argv 吞旗標掛死、stdin + --format json 串流監控 | opencode, dispatch, mannie, yargs, observability, harness |
<!-- fixindex:table:end -->

> Empty after `fixindex new <slug>` — see [docs/example-session.md](docs/example-session.md) for sample fixes.

## Adding entries

- **Same domain, new symptom:** append a `## §N` section to the matching fix file and add the symptom string to its frontmatter `symptoms:` array — that's what `fixindex find` scans.
- **New domain (≥3 expected entries):** `fixindex new <slug>` to scaffold + auto-bump the ID.
- **Deprecate:** `fixindex supersede <old> <new>` — flips `status:` to `superseded` and records the back-link; never delete the file.
