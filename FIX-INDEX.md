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

Each fix lives in `fixes/NNNN-<slug>.md` with a YAML frontmatter (`id / slug / title / tags / symptoms[] / status / supersedes[] / related[]`) and one or more `## §N {title}` sections shaped as **Symptom / Root cause / Fix / Verify**.

## Directory

<!-- fixindex:table:start -->
| ID | Slug | Title | Tags |
|----|------|-------|------|
| 0001 | lark-meeting-notes | lark-meeting-notes / audio-meeting-notes 摘要與 LLM 卡住 | lark, meeting-notes, llm, spawnSync |
| 0002 | provider-api-overload | Provider API request failed — 長思考/大 context 單請求過肥中斷 | claude-code, anthropic-api, provider, overload, context, extended-thinking |
| 0003 | free-claude-code-model-mapping | free-claude-code (fcc) sonnet/opus 映射模型持續 Provider API request failed | free-claude-code, fcc, nvidia-nim, model-routing, provider, gpt-oss-120b, thinking-injection, mistral-large, server-down |
| 0004 | git-clone-early-eof-shallow | git clone 大歷史 repo 反覆 early EOF / .invalid HEAD —— 用 shallow clone 繞過 | git, git-clone, early-eof, rpc-failed, http2-cancel, shallow-clone, depth-1, invalid-head, broken-branch, zombie-process, prophet-protocol |
| 0005 | hermes-agnes-no-final-response | Hermes 接 Agnes AI custom provider 設定 + 「no final response was produced」已知 harness bug | hermes, hermes-agent, agnes-ai, custom-provider, openai-compatible, no-final-response, content-null, tool-calls, vllm, nousresearch, cc-switch, fallback-provider |
<!-- fixindex:table:end -->

## Adding entries

- **Same domain, new symptom:** append a `## §N` section to the matching fix file and add the symptom string to its frontmatter `symptoms:` array — that's what `fixindex find` scans.
- **New domain (≥3 expected entries):** `fixindex new <slug>` to scaffold + auto-bump the ID.
- **Deprecate:** `fixindex supersede <old> <new>` — flips `status:` to `superseded` and records the back-link; never delete the file.
