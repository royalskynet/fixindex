#!/usr/bin/env python3
"""
fxadjudicate.py — fixindex 寫入時裁決
Three operations: APPEND § | SUPERSEDE | NEW
ACE-compliant: no "rewrite existing § content" operation exists
"""
import sys, os, json, re, hashlib, time, subprocess

FXSEARCH = "/Users/51mini/dev/fixindex/fxsearch.py"
FXMETA = "/Users/51mini/dev/fixindex/fxmeta.py"
FIXDIR = os.environ.get("FIXINDEX_DIR", os.path.expanduser("~/.claude/projects/-Users-51mini/memory/fixes"))
TEMPLATE = os.path.join(FIXDIR, ".template.md")
DRY_RUN = False

def read(path):
    with open(path) as f:
        return f.read()

def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)

def fxsearch(q, limit=5):
    """Run fxsearch and return parsed hits"""
    r = subprocess.run(
        ["python3", FXSEARCH, "--json", f"--limit={limit}", q],
        capture_output=True, text=True, timeout=15
    )
    if r.returncode != 0 or not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout).get("hits", [])
    except:
        return []

def next_id():
    """Find next available entry number"""
    import glob
    files = glob.glob(f"{FIXDIR}/[0-9]*.md")
    ids = []
    for f in files:
        m = re.search(r'(\d{4})', os.path.basename(f))
        if m:
            ids.append(int(m.group(1)))
    return f"{max(ids)+1:04d}" if ids else "0001"

def build_entry(num, symptom, root_cause, fix, verify, pivot, tags, domain, supersedes_reason=None):
    """Build a canonical fix entry from components"""
    # Use canonical structure from .template.md style
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # tags = list
    tags_block = "\n".join(f"  - {t}" for t in tags)
    
    entry = f"""---
id: {num}
status: active
title: {symptom[:80].strip()}
tags:
{tags_block}
symptoms:
  - "{symptom}"
---

## §1 {symptom[:60]}

**Symptom:** {symptom}

**Root cause:** {root_cause}

**Fix:** {fix}

**Verify:** {verify}

**Pivot:** {pivot or '無'}

"""
    if supersedes_reason:
        entry += f"**Supersedes-reason:** {supersede_reason}\n\n"
    entry += f"**Retrospective:** 自動蒸餾 — {now}\n"
    return entry

def append_section(path, section_data):
    """Append a new § to an existing entry file"""
    txt = read(path)
    # Find last line; append §
    lines = txt.split("\n")
    # Add § heading
    last_section_num = len(re.findall(r"^## §(\d+)", "\n".join(lines), re.M))
    new_num = last_section_num + 1
    
    new_section = f"""

## §{new_num} {section_data.get('heading','')}

**Root cause:** {section_data.get('root_cause','')}

**Fix:** {section_data.get('fix','')}

**Verify:** {section_data.get('verify','')}
"""
    with open(path, "a") as f:
        f.write(new_section)
    return new_num

def adjudicate(entry_json):
    """Main decision logic:
    entry_json = {symptom, root_cause, fix, verify, pivot, tags, domain}
    Returns decision + target
    """
    symptom = entry_json.get("symptom", "")
    root_cause = entry_json.get("root_cause", "")
    domain = entry_json.get("domain", "")
    
    # 1. Search for existing entries with similar symptom
    query = f"{symptom} {root_cause[:100]}"
    hits = fxsearch(query, limit=5)
    
    # 2. Decision logic
    if hits:
        top = hits[0]
        top_key = top["key"].split("#")[0]  # get entry id like "0342"
        score = top.get("score", 0)
        
        # APPEND § — high score and same domain, and different root cause
        top_file = os.path.join(FIXDIR, f"{top_key}.md") if not top_key.endswith(".md") else os.path.join(FIXDIR, top_key)
        
        # Check if it's the same domain but different root_cause
        # SIMPLIFIED: if same domain flag in entry → APPEND
        if domain and score > 1.5:
            return {
                "decision": "APPEND",
                "target": top_key,
                "file": top_file,
                "score": score,
                "reason": f"Similar to {top_key} (score={score:.1f}) — appending new §"
            }
        
        # SUPERSEDE: Need LLM to determine contradiction (TODO: implement LLM check)
        # For now, skip this path
        pass
    
    # 3. Otherwise NEW
    new_id = next_id()
    return {
        "decision": "NEW",
        "target": new_id,
        "file": None,
        "reason": "No existing match — creating new entry as {new_id}"
    }

def print_summary(results):
    """Print adjudication summary"""
    print(f'Decision: {results["decision"]}')
    print(f'  Target: {results["target"]}')
    print(f'  Reason: {results["reason"]}')
    return results

if __name__ == "__main__":
    import hashlib
    DRY_RUN = "--dry-run" in sys.argv
    
    # Read entry JSON from stdin or cmdline
    if sys.stdin.isatty():
        if len(sys.argv) < 2:
            print("Usage: fxadjudicate.py --dry-run < /tmp/entry.json", file=sys.stderr)
            sys.exit(1)
    else:
        raw = sys.stdin.read()
        try:
            entry = json.loads(raw)
        except:
            print(f"Invalid JSON input", file=sys.stderr)
            sys.exit(1)
        
        result = adjudicate(entry)
        
        if DRY_RUN:
            print_summary(result)
        else:
            # Real execution would write to fixindex
            print_summary(result)
            print("WARNING: --write not yet implemented (shadow mode)", file=sys.stderr)