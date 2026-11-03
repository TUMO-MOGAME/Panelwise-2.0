"""T124 variant: a pair described alike counts only when exactly one of the two is a known character
(the judge matched one figure; the copy is the other). Scored free on every stored sample.

Usage: rules2.py <repo> <twice dir> <all_audits.json>
"""

import itertools
import json
import re
import sys

REPO, TWICE, ALL = sys.argv[1:4]
STOP = set("a an the with and of in on at wearing holding her his their to is".split())


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP}


def flagged(people, calls, rule: str) -> bool:
    for i, j in itertools.combinations(range(len(people)), 2):
        known = (calls.get(i) is not None) + (calls.get(j) is not None)
        if rule == "merged" and known == 2:
            continue
        if rule == "one" and known != 1:
            continue
        x, y = words(people[i]["appearance"]), words(people[j]["appearance"])
        if x | y and len(x & y) / len(x | y) >= 0.5:
            return True
    return False


samples = {}
# 17 Oct (all attempts) + lighthouse + red-kite: as rules.py
sys.argv = ["rules.py", REPO, TWICE]
src = open(f"{TWICE}/rules.py", encoding="utf-8").read()
src = src.split("print(f\"{len(frames)} labelled attempts:")[0]
ns: dict = {}
exec(compile(src, "rules", "exec"), ns)
# rules.py's frames lack people/calls: rebuild them here
fresh = []
for a in json.load(open(f"{TWICE}/attempts.json")):
    k = f"{a['scene_index'] + 1}.{a['shot_number']}"
    lab = ns["REPORT"][a["title"]].get(f"{k}/{a['attempt']}") or ns["REPORT"][a["title"]][k]
    fresh.append((lab.rstrip("*"), lab.endswith("*"), a["people"] or [], {c["person"]: c["character"] for c in (a["calls"] or [])}))
labels = {(x["script"], x["shot"], x["attempt"]): x for x in json.load(open(f"{REPO}/eval/frame-labels.json"))["labels"]}
for script, path in (("the-lighthouse-inspector", "eval/measurements/2026-10-17/lighthouse-super-vl.json"),
                     ("the-red-kite", "eval/measurements/2026-10-18-describer/signature-slot.json")):
    for r in json.load(open(f"{REPO}/{path}"))["records"]:
        lab = labels.get((script, f"{r['scene'] + 1}.{r['shot']}", r["attempt"]))
        if lab and r.get("description") and r.get("target", "storyboard") == "storyboard":
            fresh.append((lab["label"], "drawn_twice" in (lab.get("faults") or []), r["description"]["people"],
                          {c["person"]: c["character"] for c in (r["judgement"] or {}).get("people", [])}))
samples["Super VL, stored (67)"] = fresh

idx = {}
for a in json.load(open(ALL)):
    k = (a["title"], a["k"], a["att"])
    if k not in idx or a["at"] > idx[k]["at"]:
        idx[k] = a
old = []
for k, x in labels.items():
    a = idx[k]
    old.append((x["label"], "drawn_twice" in (x.get("faults") or []), a["people"] or [],
                {c["person"]: c["character"] for c in (a["calls"] or [])}))
samples["109 labelled, stored DeepSeek-era"] = old

for name, rows in samples.items():
    copies = sum(r[1] for r in rows)
    right = sum(r[0] == "right" for r in rows)
    for rule in ("merged", "one"):
        hits = [r for r in rows if flagged(r[2], r[3], rule)]
        print(f"{name:36} {rule:6}: copies {sum(r[1] for r in hits)}/{copies}, right {sum(r[0] == 'right' for r in hits)}/{right}, "
              f"other wrong {sum(r[0] == 'wrong' and not r[1] for r in hits)}, weak {sum(r[0] == 'weak' for r in hits)}")
