---
id: 0001
slug: deploy-pipeline
title: Deploy pipeline / CI runner / artifact upload
tags: [ci,deploy,docker,github-actions]
symptoms:
  - "Error: ENOSPC: no space left on device"
  - "docker: Error response from daemon: layer does not exist"
  - "actions/upload-artifact failed with exit code 1"
  - "fatal: unable to access repo: SSL certificate problem"
  - "npm ERR! code EINTEGRITY"
status: active
supersedes: []
related: []
---
# 0001 deploy-pipeline

## §1 CI runner disk full mid-build
**Symptom:** `Error: ENOSPC: no space left on device` during `npm ci` or `docker build`
**Root cause:** Self-hosted runner accumulates layers / `node_modules` cache without GC; default runner image only ships ~14 GB free
**Fix:** Add a pre-job cleanup step:
```yaml
- name: Free disk
  run: |
    docker system prune -af --volumes || true
    sudo rm -rf /usr/share/dotnet /opt/ghc /usr/local/lib/android
    df -h
```
**Verify:** `df -h /` reports >20 GB free before the build step starts

## §2 Docker layer reference missing on push
**Symptom:** `docker: Error response from daemon: layer does not exist` on `docker push`
**Root cause:** Local registry cache was pruned between `build` and `push` steps (separate jobs)
**Fix:** Combine build + push into one job, or push to a remote registry immediately after build (don't rely on local cache crossing jobs)
**Verify:** Same workflow run logs both `Successfully built` and `digest: sha256:…` without intervening prune

## §3 artifact upload silently truncated
**Symptom:** `actions/upload-artifact` exits 0 but downloaded zip is empty
**Root cause:** Glob pattern matched zero files because previous step `cd build/` changed cwd and the upload step used a relative path resolved from the wrong dir
**Fix:** Use absolute paths in upload `path:` field, or set `working-directory` explicitly on the upload step
**Verify:** Re-run, download artifact, `unzip -l` shows expected files
**Retrospective:** The action exits 0 on zero matches — that silent-success is the trap. Future workflows should add a post-upload `gh run download` smoke check, or fail-on-empty via `if-no-files-found: error`.
