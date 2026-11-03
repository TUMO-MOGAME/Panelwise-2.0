"""The rest of the-red-kite's "what carries over" table, for the lighthouse translation run:
people described (how many), the sex agent's answers on the same people, the presence agent,
the judge's matches (person -> character), light and shot size, has_text. Prints every attempt
whose judge matches differ, with the eye label, so each can be looked at."""

import json
import sys

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
both = [k for k in a if k in b and a[k]["description"] and b[k]["description"]]
print(f"attempts {len(a)} / {len(b)}; both described: {len(both)}")

ppl = sum(len(a[k]["description"]["people"]) == len(b[k]["description"]["people"]) for k in both)
print(f"people described (how many): {ppl} of {len(both)}")
for k in both:
    na, nb = len(a[k]["description"]["people"]), len(b[k]["description"]["people"])
    if na != nb:
        print(f"   {k[0]} a{k[1]}: {na} -> {nb}")

for field in ("setting", "light", "shot_size", "has_text"):
    n = sum(a[k]["description"].get(field) == b[k]["description"].get(field) for k in both)
    print(f"{field}: {n} of {len(both)}")

qa = sum(len(a[k]["seen"]) for k in a)
qb = sum(len(b[k]["seen"]) for k in b)
same = total = 0
for k in both:
    sa = {s["character"]: s["sex"] for s in a[k]["seen"]}
    sb = {s["character"]: s["sex"] for s in b[k]["seen"]}
    for c in sa.keys() & sb.keys():
        total += 1
        if sa[c] == sb[c]:
            same += 1
        else:
            print(f"   sex differs {k[0]} a{k[1]} {c}: {sa[c]} -> {sb[c]}")
print(f"sex agent: {qa} questions / {qb}; on the same character in the same attempt {same} of {total} the same")

fa = sum(bool(a[k]["found"]) for k in a)
fb = sum(bool(b[k]["found"]) for k in b)
print(f"presence agent found someone on {fa} attempts / {fb}")
for k in both:
    if a[k]["found"] or b[k]["found"]:
        print(f"   {k[0]} a{k[1]} found DS {a[k]['found']} | VL {b[k]['found']}")


def matches(r):
    return sorted(p["character"] for p in r["judgement"]["people"] if p.get("character")) if r["judgement"] else None


m = sum(matches(a[k]) == matches(b[k]) for k in both)
print(f"judge's matches (characters matched): {m} of {len(both)} the same")
for k in sorted(both, key=lambda k: [int(x) for x in k[0].split(".")]):
    if matches(a[k]) != matches(b[k]):
        lab = labels.get(k, {})
        print(f"   {k[0]} a{k[1]} [{lab.get('label', '?')}] DS {matches(a[k])} | VL {matches(b[k])}  -- {lab.get('note', '')[:110]}")
        for name, r in (("DS", a[k]), ("VL", b[k])):
            for i, p in enumerate(r["description"]["people"]):
                print(f"        {name} person {i}: {p.get('appearance', '')[:150]}")
