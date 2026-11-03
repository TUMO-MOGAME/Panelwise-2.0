"""Compares each candidate's control answers with the stored Super VL descriptions of the same frames."""

import json
import pathlib
import sys

P = pathlib.Path(sys.argv[1])
stored = {}
for line in open(P / "t109_stored.txt", encoding="utf-8"):
    a, d = line.rstrip("\n").split("|", 1)
    stored[a] = json.loads(d)


def shape(d):
    return f"p{len(d['people'])} o{len(d['objects'])} {d['setting']} t{len(d['text'])}"


for line in open(P / "t109_controls.txt", encoding="utf-8"):
    label, asset = line.split()
    s = stored[asset]
    row = [f"{label:20}", f"stored {shape(s)}"]
    for v in ("base", "capsfmt"):
        d = json.loads((P / "t109b" / f"{v}-{label.replace(':', '__')}-r1.txt").read_text(encoding="utf-8"))
        row.append(f"{v}: {'IDENTICAL' if d == s else shape(d)}")
    print(" | ".join(row))
