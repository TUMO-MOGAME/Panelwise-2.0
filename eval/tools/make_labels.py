"""Writes eval/frame-labels.json: every stored drawing we looked at by eye, with our verdict.

Sources (each label says which): the learning log's entries (docs/learning-log.md), the 2026-10-14
rule what-if (L021: no_character, setting, unscripted_object on nine runs), the held-out runs of
the-lighthouse-inspector and the-borrowed-bicycle (L022, L023), and the 2026-10-16 measurements of
T102 (a found person's sex) and T104 (split panels, one person drawn twice). Run from the repo
root: python eval/tools/make_labels.py
"""

import json
from pathlib import Path

# label: right (the frame shows the shot), weak (the shot, with something missing or extra that the
# script didn't write), wrong (it shows something the script contradicts, or isn't the shot).
# faults: what is wrong, in the audit's words where a check exists for it.
FAULTS = {
    "drawn_sex": "a character drawn as the other sex",
    "absent": "none of the shot's drawn characters is in the frame",
    "split_panels": "drawn as a strip or grid of panels",
    "drawn_twice": "one person drawn twice in one picture",
    "extra_person": "a person the script doesn't put there",
    "setting": "inside for an EXT scene, or outside for an INT one",
    "age": "a character drawn at the wrong age",
    "missing_prop": "a thing the shot names isn't drawn",
    "missing_action": "the shot's action isn't drawn",
    "empty_frame": "a frame for a line whose speaker is only heard: no one or nothing to show",
    "wrong_character": "the person drawn is a different character",
    "unclear_sex": "a character whose sex the script gives, drawn so it can't be told",
}

L: list[dict[str, object]] = []


def add(script: str, shot: str, attempt: int, label: str, faults: list[str], note: str, source: str) -> None:
    assert label in ("right", "weak", "wrong"), label
    assert all(f in FAULTS for f in faults), faults
    L.append({"script": script, "shot": shot, "attempt": attempt, "label": label,
              "faults": faults, "note": note, "source": source})


# --- L021 / L020: the rule what-if, 2026-10-14 (frames NO_CHARACTER, SETTING or UNSCRIPTED_OBJECT
# would withhold; every one looked at). "real" = the frame truly lacks what the rule says.
W = "L021 what-if (2026-10-14)"
for script, shot, note in [
    ("final-whistle", "2.3", "no crowd"),
    ("final-whistle", "3.3", "the referee isn't drawn as the script's referee"),
    ("final-whistle", "4.3", "Lindi drawn, not Palesa"),
    ("load-shedding", "2.1", "an empty classroom (an adult from behind, taken for LUCKY)"),
    ("lost-property", "7.4", "one man, no Tebogo or officer"),
    ("stormwater", "5.1", "only the dog"),
    ("the-bread-van", "4.1", "no taxi driver; Betty not on the step"),
]:
    add(script, shot, 1, "wrong", ["absent"], note, W + ": no_character real")
add("lost-property", "9.4", 1, "wrong", ["absent", "split_panels"], "split panel, no Priya", W + ": no_character real; T104 split")
for script, shot in [
    ("final-whistle", "1.4"), ("final-whistle", "2.1"), ("final-whistle", "2.2"), ("final-whistle", "5.3"),
    ("final-whistle", "6.2"), ("load-shedding", "5.2"), ("lost-property", "2.1"), ("market-day", "2.1"),
    ("market-day", "3.2"), ("sipho-and-siphokazi", "2.3"), ("stormwater", "2.2"), ("stormwater", "6.1"),
    ("the-bread-van", "2.4"), ("the-bread-van", "3.1"), ("the-bread-van", "3.3"), ("the-bread-van", "4.4"),
    ("the-night-taxi", "1.1"), ("the-night-taxi", "2.1"), ("the-night-taxi", "2.4"),
]:
    add(script, shot, 1, "right", [], "the cast is drawn; the judge didn't match them", W + ": no_character false alarm")
add("lost-property", "3.2", 1, "wrong", ["drawn_sex"], "Priya drawn as a man (present, the wrong sex)", W + ": no_character false alarm")
add("stormwater", "6.4", 1, "wrong", ["age"], "Mr. Van der Merwe drawn young (present, the wrong age)", W + ": no_character false alarm")
add("the-night-taxi", "5.4", 1, "wrong", ["age"], "BONGANI (50s) drawn a teenager, UNCLE SIZWE (30s) old", W + ": no_character false alarm")
for script, shot in [("the-bread-van", "2.2"), ("the-bread-van", "2.4"), ("the-bread-van", "4.5")]:
    add(script, shot, 1, "wrong", ["setting"], "an EXT scene drawn indoors", W + ": setting real")
for script, shot, note in [
    ("lost-property", "5.1", "an INT covered platform, open-looking"),
    ("lost-property", "7.3", "an INT covered platform, open-looking"),
    ("lost-property", "12.2", "an EXT platform with a roof"),
    ("sipho-and-siphokazi", "2.1", "an open bait shack"),
    ("stormwater", "5.1", "the tunnels"),
]:
    add(script, shot, 1, "right", [], note, W + ": setting false alarm")
add("lost-property", "5.3", 1, "right", [], "a police baton on an officer's belt", W + ": unscripted_object false alarm")
add("the-red-kite", "2.2", 1, "right", [], "a knife on the workbench", W + ": unscripted_object false alarm")

# --- L022: the-lighthouse-inspector, held out, 2026-10-14 (all 26 shown at attempt 1, each looked at).
H = "L022 held-out run (2026-10-14)"
for shot in ["1.1", "2.1", "3.1", "3.2", "3.3", "3.4", "4.3", "5.2", "5.3", "6.2", "6.3", "7.2", "9.2", "9.3"]:
    add("the-lighthouse-inspector", shot, 1, "right", [], "", H)
for shot, faults, note in [
    ("4.1", ["extra_person"], "an extra man on the stairs"),
    ("4.2", ["drawn_twice"], "Ms. Naidoo drawn twice (two women in suits); T104's question misses it"),
    ("7.3", ["drawn_twice"], "Ms. Naidoo drawn twice; T104's question misses it"),
    ("5.1", ["missing_prop"], "the lens room without its lens"),
    ("8.1", ["missing_prop"], "no rescue boat"),
    ("2.2", ["missing_prop", "missing_action"], "props or actions missing"),
    ("6.1", ["missing_prop", "missing_action"], "props or actions missing"),
    ("9.1", ["missing_prop", "missing_action"], "props or actions missing"),
    ("2.3", ["empty_frame"], "a heard-only speaker's line"),
    ("7.4", ["empty_frame"], "a heard-only speaker's line"),
    ("7.1", ["unclear_sex"], "an old person of unclear sex for the bare FORTUIN (T101 folds it into MR. FORTUIN)"),
]:
    add("the-lighthouse-inspector", shot, 1, "weak", faults, note, H)
add("the-lighthouse-inspector", "7.5", 1, "wrong", ["drawn_sex"],
    "Mr. Fortuin drawn as an old woman; found by the presence agent, now asked its sex (T102)", H + "; T102")

# --- L023: the-borrowed-bicycle, held out, 2026-10-14.
B = "L023 held-out run (2026-10-14)"
for shot in ["1.1", "1.2", "1.3", "2.1", "2.3", "3.1", "3.2", "4.1", "4.3", "5.2"]:
    add("the-borrowed-bicycle", shot, 1, "wrong", ["drawn_sex"], "NALEDI (12) drawn as a boy", B)
add("the-borrowed-bicycle", "5.1", 1, "wrong", ["drawn_sex", "extra_person"], "NALEDI drawn as a boy; extra children", B)
add("the-borrowed-bicycle", "4.2", 1, "wrong", ["extra_person"], "a naked adult man for \"They sit up\" (no figure in the prompt)", B)
for shot, note in [("2.2", "the shopkeeper and his newspaper"), ("3.3", "the puddle"), ("5.4", "")]:
    add("the-borrowed-bicycle", shot, 1, "right", [], note, B)
add("the-borrowed-bicycle", "5.5", 1, "weak", ["empty_frame"], "an empty yard for a line", B)

# --- T102 (2026-10-16): a found person asked its sex; the flags, each looked at.
T2 = "T102 measurement (2026-10-16)"
add("sipho-and-siphokazi", "2.1", 2, "wrong", ["drawn_sex"], "MAMA THEMBI drawn as an old man", T2)
add("the-night-taxi", "2.3", 2, "wrong", ["missing_action", "unclear_sex"],
    "a child at the taxi's wheel; THABO at the window reads as a girl (arguable)", T2)

# --- T104 (2026-10-16): the layout question's flags on 332 attempts, each looked at with its cast.
T4 = "T104 measurement (2026-10-16)"
for script, shot, attempt in [
    ("lost-property", "11.5", 1), ("lost-property", "11.5", 2), ("lost-property", "11.5", 3),
    ("lost-property", "12.2", 2), ("lost-property", "2.2", 2), ("lost-property", "9.2", 3),
    ("lost-property", "9.4", 2), ("lost-property", "9.6", 2),
    ("market-day", "4.2", 1), ("market-day", "5.2", 1), ("sipho-and-siphokazi", "7.1", 1),
    ("sipho-and-siphokazi", "7.1", 3), ("sipho-and-siphokazi", "9.2", 3), ("the-bread-van", "1.2", 3),
    ("the-bread-van", "1.3", 1), ("the-bread-van", "1.3", 2), ("the-night-taxi", "1.2", 3),
    ("the-night-taxi", "5.1", 1), ("the-night-taxi", "5.1", 2), ("the-night-taxi", "6.3", 1),
    ("the-night-taxi", "6.3", 2), ("the-red-kite", "5.2", 1),
]:
    add(script, shot, attempt, "wrong", ["split_panels"], "two or more panels", T4)
for script, shot, attempt, note in [
    ("the-night-taxi", "1.4", 1, "THABO drawn three times"),
    ("the-red-kite", "4.1", 1, "LERATO drawn twice in the alley"),
    ("lost-property", "7.3", 1, "TEBOGO drawn twice (KOOS is the 70s night cleaner)"),
    ("lost-property", "9.1", 3, "PRIYA drawn twice (the judge matched one to TEBOGO)"),
    ("the-bread-van", "4.4", 1, "three boys for THEO alone"),
    ("the-borrowed-bicycle", "5.2", 1, "two children for NALEDI alone, both drawn as boys"),
]:
    add(script, shot, attempt, "wrong", ["drawn_twice"], note, T4)
add("final-whistle", "6.1", 1, "right", [], "PALESA and LINDI, two look-alike girls: not a copy", T4)
add("stormwater", "3.1", 2, "wrong", ["drawn_sex"], "two boys for SIBUSISO and REFILWE: Refilwe drawn as a boy", T4)

# Several sources can name one frame: merge them (the worst label, every fault, every note).
RANK = {"right": 0, "weak": 1, "wrong": 2}
merged: dict[tuple[str, str, int], dict[str, object]] = {}
for entry in L:
    key = (str(entry["script"]), str(entry["shot"]), int(entry["attempt"]))  # type: ignore[arg-type]
    if key not in merged:
        merged[key] = dict(entry)
        continue
    m = merged[key]
    if RANK[str(entry["label"])] > RANK[str(m["label"])]:
        m["label"] = entry["label"]
    m["faults"] = sorted(set(m["faults"]) | set(entry["faults"]))  # type: ignore[arg-type]
    m["note"] = "; ".join(x for x in (str(m["note"]), str(entry["note"])) if x)
    m["source"] = f"{m['source']}; {entry['source']}"

out = {
    "_about": (
        "Every stored drawing we looked at by eye, with our verdict: right (the frame shows the shot), "
        "weak (the shot, with something missing or extra the script didn't write), wrong (it shows "
        "something the script contradicts, or isn't the shot). Keyed by script title (the newest stored "
        "run of it on Tumo's machine), shot (scene.number) and attempt. faults use the vocabulary in "
        "_faults. Score an audit against it with eval/tools/score_labels.py; the frames' data is in "
        "eval/labelled/ (eval/tools/export_labelled.py)."
    ),
    "_faults": FAULTS,
    "labels": sorted(merged.values(), key=lambda e: (e["script"], [int(x) for x in str(e["shot"]).split(".")], e["attempt"])),
}
Path("eval/frame-labels.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
counts: dict[str, int] = {}
for e in out["labels"]:  # type: ignore[union-attr]
    counts[str(e["label"])] = counts.get(str(e["label"]), 0) + 1  # type: ignore[index]
print(len(out["labels"]), "frames", counts)  # type: ignore[arg-type]
