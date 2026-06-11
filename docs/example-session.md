# Example session

A realistic shell transcript of `fixindex` catching a recurring bug.

## Scenario

Wednesday morning. CI pipeline goes red again on the staging branch. The error message looks familiar but you can't remember whether you've seen it before.

```console
$ tail -5 ci.log
2026-06-11T08:14:22Z ERROR  step="docker push" exit=1
docker: Error response from daemon: layer does not exist.
See 'docker push --help'.
```

## Look it up

```console
$ fixindex find "layer does not exist"
## symptoms match:
  0001-deploy-pipeline            L9       - "docker: Error response from daemon: layer does not exist"

(use `fixindex grep 'layer does not exist'` for full-text search)
```

One hit. Open it.

```console
$ fixindex show 0001 | sed -n '/§2/,/§3/p'
## §2 Docker layer reference missing on push
**Symptom:** `docker: Error response from daemon: layer does not exist` on `docker push`
**Root cause:** Local registry cache was pruned between `build` and `push` steps (separate jobs)
**Fix:** Combine build + push into one job, or push to a remote registry immediately after build (don't rely on local cache crossing jobs)
**Verify:** Same workflow run logs both `Successfully built` and `digest: sha256:…` without intervening prune
```

Two minutes from `grep`ing the log to a known fix. You'd written this six months ago after the same incident.

## After solving something new

Same afternoon, you find a brand-new failure mode in the same domain — a runner that hits the API rate limit on artifact download. You append to the same file:

```console
$ $EDITOR fixes/0001-deploy-pipeline.md
# add a `## §4 GitHub artifact download throttled` block
# add "API rate limit exceeded" to the symptoms: array in the frontmatter
$ ./fixindex find "API rate limit"
## symptoms match:
  0001-deploy-pipeline            L12      - "API rate limit exceeded"
```

No `re-index` needed — you only touched a domain file, not the file count. The index table only needs regeneration when you add or rename a file.

## A genuinely new domain

A few weeks later, the project picks up Redis Cluster, and you hit your first slot-migration bug.

```console
$ fixindex new redis-cluster
/Users/you/dev/fixindex/fixes/0004-redis-cluster.md
re-indexed: /Users/you/dev/fixindex/FIX-INDEX.md

$ $EDITOR fixes/0004-redis-cluster.md
# fill in title, tags, first symptoms[], §1
```

`FIX-INDEX.md` now lists `0004-redis-cluster` in the directory table. From now on, `fixindex find "MOVED"` jumps straight here.
