"""Drawn-twice: candidate rules scored on stored Super VL audits against the hand labels (free).

Samples: the 17 Oct runs (gogos-recipe, rooftop-tomatoes: every attempt, labels from their run
reports), the-lighthouse-inspector (2026-10-17 measurement) and the-red-kite (2026-10-18
signature-slot measurement), labelled frames only, from eval/frame-labels.json.

Rule W(t): a pair of described people whose appearance words overlap >= t (Jaccard, stop words
out), at least one of them matched to no character by the judge.
Rule U: unscripted_person failed (today's check).
"""

import itertools
import json
import re
import sys

REPO, TWICE = sys.argv[1], sys.argv[2]
STOP = set("a an the with and of in on at wearing holding her his their to is".split())


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP}


def best_pair(people, calls) -> float:
    best = 0.0
    for i, j in itertools.combinations(range(len(people)), 2):
        if calls.get(i) is not None and calls.get(j) is not None:
            continue
        a, b = words(people[i]["appearance"]), words(people[j]["appearance"])
        if a | b:
            best = max(best, len(a & b) / len(a | b))
    return best


frames = []  # (sample, key, label, twice?, best overlap, unscripted failed)

# 17 Oct runs: every attempt; labels by hand from the run reports (shot -> label, twice)
REPORT = {
    "gogos-recipe": {"1.1": "weak", "1.2": "right", "1.3": "right", "1.4/1": "wrong", "1.4/2": "wrong*",
                     "2.1": "wrong*", "2.2": "right", "2.3": "right", "3.1": "weak", "3.2": "wrong",
                     "3.3": "right", "3.4": "wrong*", "4.1": "right", "4.2": "right", "5.1": "weak",
                     "5.2": "right", "5.3": "wrong*", "5.4": "weak"},
    "rooftop-tomatoes": {"1.1": "right", "1.2": "weak", "2.1": "right", "2.2": "weak", "2.3": "right",
                         "3.1": "wrong*", "3.2": "right", "3.3": "wrong", "4.1": "weak", "4.2": "right",
                         "4.3": "wrong*", "5.1": "weak", "5.2": "weak", "5.3": "right", "6.1": "right",
                         "6.2": "wrong*", "6.3": "right", "7.1": "weak", "7.2": "right", "7.3": "right",
                         "7.4": "right"},
}
checks = {(c["title"], c["k"], c["att"]): c["failed"] or [] for c in json.load(open(f"{TWICE}/checks.json"))}
for a in json.load(open(f"{TWICE}/attempts.json")):
    k = f"{a['scene_index'] + 1}.{a['shot_number']}"
    lab = REPORT[a["title"]].get(f"{k}/{a['attempt']}") or REPORT[a["title"]][k]
    calls = {c["person"]: c["character"] for c in (a["calls"] or [])}
    frames.append(("17oct", f"{a['title']} {k} a{a['attempt']}", lab.rstrip("*"), lab.endswith("*"),
                   best_pair(a["people"] or [], calls),
                   "unscripted_person" in checks[(a["title"], k, a["attempt"])]))

# Lighthouse and red-kite: labelled frames only
labels = json.load(open(f"{REPO}/eval/frame-labels.json"))
labels = labels["labels"]
by_key = {(x["script"], x["shot"], x["attempt"]): x for x in labels}
for sample, script, path in (
    ("lighthouse", "the-lighthouse-inspector", "eval/measurements/2026-10-17/lighthouse-super-vl.json"),
    ("red-kite", "the-red-kite", "eval/measurements/2026-10-18-describer/signature-slot.json"),
):
    for r in json.load(open(f"{REPO}/{path}"))["records"]:
        if r.get("target", "storyboard") != "storyboard" or not r.get("description"):
            continue
        shot = f"{r['scene'] + 1}.{r['shot']}" if isinstance(r["scene"], int) else f"{r['scene']}.{r['shot']}"
        lab = by_key.get((script, shot, r["attempt"]))
        if lab is None:
            continue
        calls = {c["person"]: c["character"] for c in (r["judgement"] or {}).get("people", [])}
        failed = {f[0] if isinstance(f, list) else f for f in r["failed"]}
        frames.append((sample, f"{script} {shot} a{r['attempt']}", lab["label"],
                       "drawn_twice" in (lab.get("faults") or []),
                       best_pair(r["description"]["people"], calls), "unscripted_person" in failed))

print(f"{len(frames)} labelled attempts:",
      {s: sum(f[0] == s for f in frames) for s in ("17oct", "lighthouse", "red-kite")},
      "| copies:", sum(f[3] for f in frames), "| right:", sum(f[2] == "right" for f in frames))


def score(name, hit):
    h = [f for f in frames if hit(f)]
    copies = sum(f[3] for f in h)
    other_wrong = sum(f[2] == "wrong" and not f[3] for f in h)
    print(f"{name:12} flags {len(h):3}: copies {copies}/{sum(f[3] for f in frames)}, other wrong "
          f"{other_wrong}, weak {sum(f[2] == 'weak' for f in h)}, RIGHT {sum(f[2] == 'right' for f in h)}")


score("U (today)", lambda f: f[5])
for t in (0.4, 0.5, 0.6, 0.7, 0.8):
    score(f"W({t})", lambda f, t=t: f[4] >= t)
print("\ncopies and their overlap:")
for f in frames:
    if f[3]:
        print(f"  {f[1]:42} {f[4]:.2f}  unscripted={f[5]}")
print("right or weak frames at overlap >= 0.5:")
for f in frames:
    if not f[3] and f[2] != "wrong" and f[4] >= 0.5:
        print(f"  {f[2]:5} {f[1]:42} {f[4]:.2f}")
