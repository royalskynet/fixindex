---
id: 0003
slug: tls-and-tunnels
title: TLS / reverse proxy / tunnel webhook drift
tags: [tls,nginx,cloudflare,tunnel,webhook]
symptoms:
  - "SSL_ERROR_SYSCALL"
  - "x509: certificate signed by unknown authority"
  - "502 Bad Gateway"
  - "context canceled"
  - "webhook delivery failed: HTTP 400"
  - "ERR_TOO_MANY_REDIRECTS"
status: active
supersedes: []
related: []
---
# 0003 tls-and-tunnels

## §1 Cloudflare quick tunnel URL rotates after restart, webhook receivers miss events
**Symptom:** `webhook delivery failed: HTTP 400` from upstream provider; service responded fine when curl'd locally
**Root cause:** `cloudflared tunnel --url …` returns a fresh `*.trycloudflare.com` hostname on every restart; the receiver still points at the old one
**Fix:** Either provision a named tunnel (`cloudflared tunnel create`) with a stable DNS record, or add a post-start hook that PUTs the new URL to the receiver's webhook endpoint API
**Verify:** Restart tunnel, run `curl -s $RECEIVER_API/webhook/endpoint` and confirm the URL matches `cloudflared`'s announced one
**Retrospective:** Quick tunnels were treated as "good enough for prod" because they worked at first; named tunnels were postponed as ops work. The recurrence cost more hours than the migration would have. Rule: if a tunnel survives one outage round-trip, schedule the named-tunnel promotion the same week.

## §2 Self-signed cert in dev rejected by Go HTTP client
**Symptom:** `x509: certificate signed by unknown authority` from a service-to-service call in staging
**Root cause:** Dev cluster uses a private CA that isn't in the system trust store of the calling pod's base image
**Fix:** Mount the CA bundle into `/etc/ssl/certs/ca-certificates.crt` via a `ConfigMap`, or set `SSL_CERT_FILE` env var. Do **not** disable TLS verification in code.
**Verify:** `openssl s_client -connect target:443 -CAfile /etc/ssl/certs/ca-certificates.crt </dev/null` returns `Verify return code: 0 (ok)`

## §3 Nginx in front of a tunnel returns 502 immediately after deploy
**Symptom:** `502 Bad Gateway` from Nginx; upstream service is healthy on its loopback port
**Root cause:** Nginx resolved the upstream host once at startup and cached the IP; the upstream's IP changed on redeploy
**Fix:** Use a variable in `proxy_pass` to force re-resolution per request:
```nginx
resolver 127.0.0.11 valid=10s;
set $upstream http://backend.internal:8080;
proxy_pass $upstream;
```
**Verify:** Restart upstream, observe new IP picked up within 10 s without an Nginx reload
