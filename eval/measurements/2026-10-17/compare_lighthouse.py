"""Compares the two translation runs (Katlego's measure.py output): verdict counts, hosted-ladder
verdicts, the attempts whose failed hard checks differ, tokens and seconds, and the describer's
text/setting/people differences, with our labels for each attempt."""

import json
import statistics
import sys
from collections import Counter

ds = json.load(open(sys.argv[1], encoding="utf-8"))
vl = json.load(open(sys.argv[2], encoding="utf-8"))
labels = {
    (e["shot"], e["attempt"]): e
    for e in json.load(open(sys.argv[3], encoding="utf-8"))["labels"]
    if e["script"] == "the-lighthouse-inspector"
}


def key(r):
    return (f"{r['scene'] + 1}.{r['shot']}", r["attempt"])


a = {key(r): r for r in ds["records"]}
b = {key(r): r for r in vl["records"]}
print("attempts", len(a), len(b))
for name, run in (("DeepSeek", a), ("Super VL", b)):
    toks = [r['usage']['prompt_tokens'] + r['usage']['completion_tokens'] for r in run.values()]
    secs = [r["secs"] for r in run.values()]
    print(f"{name:9} raw {dict(Counter(r['raw'] for r in run.values()))} hosted {dict(Counter(r['hosted'] for r in run.values()))} "
          f"tokens {sum(toks):,} median secs {statistics.median(secs):.1f} errors {sum(r['raw'] == 'error' for r in run.values())}")
print()
print("attempt  label  stored  DS hosted / failed            | VL hosted / failed")
for k in sorted(a, key=lambda k: ([int(x) for x in k[0].split('.')], k[1])):
    x, y = a[k], b.get(k)
    fx = sorted(c for c, s in x['failed'] if s == 'hard'); fy = sorted(c for c, s in y['failed'] if s == 'hard') if y else ['-']
    lab = labels.get(k, {})
    mark = "*" if (fx != fy or x["hosted"] != (y or {}).get("hosted")) else " "
    print(f"{mark}{k[0]:5} a{k[1]} {lab.get('label','?'):5} {x['stored']:5} {x['hosted']:5} {','.join(fx) or '-':28} | "
          f"{(y or {}).get('hosted','?'):5} {','.join(fy) or '-':28} {lab.get('note','')[:60]}")
print()
for k in sorted(a):
    x, y = a[k], b[k]
    dx, dy = x["description"] or {}, y["description"] or {}
    diffs = []
    if dx.get("setting") != dy.get("setting"):
        diffs.append(f"setting {dx.get('setting')} -> {dy.get('setting')}")
    if len(dx.get("people", [])) != len(dy.get("people", [])):
        diffs.append(f"people {len(dx.get('people', []))} -> {len(dy.get('people', []))}")
    if len(dx.get("text", [])) != len(dy.get("text", [])):
        diffs.append(f"text {len(dx.get('text', []))} -> {len(dy.get('text', []))}")
    if dx.get("signature") != dy.get("signature"):
        diffs.append(f"signature {dx.get('signature')} -> {dy.get('signature')}")
    if diffs:
        print(f"  {k[0]} a{k[1]}: " + "; ".join(diffs))
