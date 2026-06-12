---
id: 0002
slug: postgres-migrations
title: PostgreSQL migrations / locking / connection pool
tags: [postgres,migrations,locking,connection-pool]
symptoms:
  - "ERROR: deadlock detected"
  - "could not obtain lock on relation"
  - "remaining connection slots are reserved"
  - "FATAL: sorry, too many clients already"
  - "relation \"...\" does not exist"
  - "current transaction is aborted, commands ignored until end of transaction block"
status: active
supersedes: []
related: []
---
# 0002 postgres-migrations

## §1 ALTER TABLE blocks on long-running transaction
**Symptom:** Migration hangs forever on `ALTER TABLE … ADD COLUMN`, then `could not obtain lock on relation`
**Root cause:** Another session holds an `AccessShareLock` from a long-running `SELECT` (often an autovacuum or a leaked connection from the API)
**Fix:** Set a lock timeout before the migration, retry-on-failure:
```sql
SET lock_timeout = '5s';
ALTER TABLE users ADD COLUMN trial_ends_at TIMESTAMPTZ;
```
Then identify the blocker: `SELECT pid, query, state, xact_start FROM pg_stat_activity WHERE state != 'idle' ORDER BY xact_start;`
**Verify:** Migration completes; `pg_locks` view shows no `AccessExclusiveLock` left over
**Retrospective:** Past migrations also blocked silently — we relied on "it ran fine in staging" without checking staging had no long-running readers. Add a CI gate that runs every migration against a workload-replayed staging clone before merging.

## §2 Connection pool exhausted under load test
**Symptom:** `FATAL: sorry, too many clients already` from the API during traffic spike
**Root cause:** App opens a new pool per request handler instead of sharing one, multiplied by N replicas
**Fix:** Single global pool with `max=20`, plus PgBouncer in `transaction` pooling mode in front of Postgres
**Verify:** `SELECT count(*) FROM pg_stat_activity WHERE datname='app';` stays under `max_connections * 0.7` at peak

## §3 Idempotent UP migration breaks DOWN
**Symptom:** Repeated `migrate up` works, but `migrate down` fails with `relation "old_name" does not exist`
**Root cause:** UP used `CREATE TABLE IF NOT EXISTS`, but DOWN used plain `DROP TABLE` without `IF EXISTS`
**Fix:** Mirror idempotency on both sides: `DROP TABLE IF EXISTS old_name;`
**Verify:** `migrate up && migrate down && migrate up` round-trip succeeds
