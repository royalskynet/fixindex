#!/usr/bin/env python3
"""
fxblurb.py v3 — LLM 生成 contextual blurb + VOCAB term expansion via OmniRoute 20130
Uses subprocess with stdin pipe (avoids shell escaping / big argv issues)
"""
import json, sys, os, hashlib, time, re, subprocess, textwrap

API_URL = "http://127.0.0.1:20130/v1/chat/completions"
API_KEY = os.environ.get("OMNIROUTE_API_KEY", "omniro-route-internal-key-placeholder")
MODEL = "free-tools-heavy"
FIXDIR = os.environ.get("FIXINDEX_DIR", os.path.expanduser("~/.claude/projects/-Users-51mini/memory/fixes"))
BLURB_PATH = os.path.join(FIXDIR, ".blurbs.jsonl")

def fetch_blurb(section_text, section_heading=""):
    """Return (blurb_text, vocab_list, finish_reason, completion_tokens); on failure blurb_text is ""."""
    prompt = f"""You are indexing a coding bug knowledge base.
Below is ONE SECTION of an entry titled "{section_heading}".
Return ONLY valid JSON, no other text, no markdown fences:
{{"blurb":"2-3 sentence Chinese explanation of what this section tracks and when to use it","vocab":["word1","word2",...]}}

The VOCAB field should be 8-15 search terms a developer might type to find this section,
but that DO NOT appear literally in the text. Include: synonyms, English/Chinese equivalents,
higher-level concepts, related CLI tools, error message variants, file names.

SECTION TEXT:
{section_text[:3500]}
"""

    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 4000,
        "stream": False,
        "reasoning_effort": "none"
    }).encode()

    try:
        r = subprocess.run([
            "curl", "-sf", "-m180",
            "-H", f"Authorization: Bearer {API_KEY}",
            "-H", "Content-Type: application/json",
            "-d", "@-",
            API_URL
        ], input=body, capture_output=True, timeout=160)
        if r.returncode != 0:
            return "", [], None, None
        data = json.loads(r.stdout)
        # Safely extract content
        content = None
        finish_reason = None
        completion_tokens = None
        if isinstance(data, dict):
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                finish_reason = choices[0].get("finish_reason")
                usage = data.get("usage") or {}
                completion_tokens = usage.get("completion_tokens")
                # Try content first, then reasoning_content (for reasoning models)
                content = message.get("content")
                if not content:
                    content = message.get("reasoning_content")
        if not content:
            # No content returned; treat as failure
            return "", [], finish_reason, completion_tokens
        # Ensure content is string
        if not isinstance(content, str):
            # If it's a list or dict, try to json.dumps it? but spec expects string.
            # We'll attempt to convert via str()
            content = str(content)
        content = content.strip()
        # match JSON in response
        m = re.search(r'\{[^{}]*\}', content)
        if m:
            parsed = json.loads(m.group(0))
            return parsed.get("blurb", ""), parsed.get("vocab", []), finish_reason, completion_tokens
        # fallback: try to parse the entire content as JSON
        try:
            parsed = json.loads(content)
            return parsed.get("blurb", ""), parsed.get("vocab", []), finish_reason, completion_tokens
        except Exception:
            return "", [], finish_reason, completion_tokens
    except Exception as e:
        print(f"  [ERR/{section_heading[:40]}]: {e}", file=sys.stderr)
        return "", [], None, None
def backfill(force=False, limit=0):
    """backfill blurbs. limit=0 means unlimited."""
    import glob
    import importlib.util
    spec = importlib.util.spec_from_file_location("fxmeta", os.path.join(os.path.dirname(__file__), "fxmeta.py"))
    fxmeta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fxmeta)

    hashes = set()
    if os.path.exists(BLURB_PATH) and not force:
        with open(BLURB_PATH) as f:
            for line in f:
                if line.strip():
                    hashes.add(json.loads(line).get("hash", ""))

    files = sorted(glob.glob(f"{FIXDIR}/[0-9]*.md"))
    if limit:
        files = files[:limit]

    count = 0
    with open(BLURB_PATH, "a") as bf:
        for fp in files:
            fn = os.path.basename(fp).replace(".md", "")
            txt = open(fp).read()
            fm, body_start = fxmeta.parse_frontmatter_full(txt)
            sections = fxmeta.get_sections(txt, body_start)
            for i, sec in enumerate(sections):
                h = hashlib.sha1(sec["content"].encode()).hexdigest()[:12]
                if h in hashes and not force:
                    continue
                key = f"{fn[:4]}#{i+1}"
                blurb, vocab, finish_reason, completion_tokens = fetch_blurb(sec["content"], sec["heading"])
                if not blurb:
                    print(f"  skip {key}: finish={finish_reason} tokens={completion_tokens}", file=sys.stderr)
                    continue
                entry = {"key": key, "hash": h, "heading": sec["heading"], "blurb": blurb, "vocab": vocab, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                bf.write(json.dumps(entry, ensure_ascii=False) + "\n")
                bf.flush()
                count += 1
                print(f"  [{count}] {key}: {blurb[:60]}...", file=sys.stderr)
    print(f"Generated {count} new blurbs", file=sys.stderr)

if __name__ == "__main__":
    force = "--force" in sys.argv
    limit = 0
    for a in sys.argv:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    backfill(force=force, limit=limit)