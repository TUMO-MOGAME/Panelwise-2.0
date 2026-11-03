"""Scores an audit against the frames we labelled by eye (eval/frame-labels.json), so a change to
the audit (a new vision model, a new rule, a new agent) is measured on the same drawings and the
same verdicts as every change before it.

    # in the API container (it reads Storage and calls Token Factory), the repo mounted at /work:
    python /work/eval/tools/score_labels.py /work                 # today's audit, re-run: Token Factory
    python /work/eval/tools/score_labels.py /work --stored        # the audits stored then: free
    python /work/eval/tools/score_labels.py /work --script the-lighthouse-inspector --json out.json

Today's audit is `audit_frame` with this process's settings (NEBIUS_MODEL_VISION,
NEBIUS_VISION_THINKING, ...), then the rule ladder (AUDIT_WITHHOLD_CHECKS), as the loop applies it.
`--stored` reads each attempt's stored checks and applies today's ladder to them. Nothing is written
and nothing is drawn: about 1,000-2,000 Token Factory tokens a frame for a re-run.

A frame is *withheld* when its laddered verdict is FAIL or ERROR, else *shown*. Against the labels:
a wrong frame withheld is caught, shown is missed; a right frame withheld is a false alarm. Weak
frames are reported apart (the audit isn't asked to withhold them). Per fault, the checks that
failed on it, so a fault the audit sees for the wrong reason shows up.
"""

import argparse
import asyncio
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx2
from PIL import Image

from app.core.config import Settings, withholding
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.storage import SupabaseStore
from app.verify.audit import apply_ladder, audit_frame
from app.verify.model import Audit, Check, CheckResult, RenderedFrame, Severity, Verdict
from app.llm import Usage


def stored_audit(frame: dict[str, Any]) -> Audit:
    stored = frame["stored_audit"]
    checks = tuple(
        CheckResult(Check(c["check"]), Severity(c["severity"]), bool(c["ok"]), str(c["detail"]))
        for c in stored["checks"] or ()
        if c["check"] in Check.__members__.values()
    )
    shot = tuple(int(x) for x in frame["shot"].split("."))
    return Audit((shot[0] - 1, shot[1]), frame["attempt"], frame["seed"], None, None, checks,
                 Verdict(stored["verdict"]) if stored["verdict"] != "error" else Verdict.ERROR,
                 {}, tuple(stored["models"] or ()), Usage(0, 0, 0))  # fmt: skip


def failed(audit: Audit) -> list[str]:
    return [c.check.value for c in audit.checks if not c.ok and c.severity is Severity.HARD]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--stored", action="store_true", help="score the stored audits; no model call")
    ap.add_argument("--script", action="append", help="only these scripts (repeatable)")
    ap.add_argument("--json", type=Path, help="write every frame's result here")
    args = ap.parse_args()

    labels = json.loads((args.root / "eval/frame-labels.json").read_text(encoding="utf-8"))["labels"]
    settings = Settings()
    ladder = withholding(settings)
    model = None if args.stored else NebiusChatModel.from_settings(settings)
    results: list[dict[str, Any]] = []
    async with httpx2.AsyncClient(timeout=120) as client:
        store = SupabaseStore(url=settings.supabase_url, secret_key=settings.supabase_secret_key,
                              bucket=settings.supabase_storage_bucket, client=client)  # fmt: skip
        for path in sorted((args.root / "eval/labelled").glob("*.json")):
            bundle = json.loads(path.read_text(encoding="utf-8"))
            if args.script and bundle["script"] not in args.script:
                continue
            sp = load_screenplay(bundle["screenplay"])
            ex = load_extraction(bundle["extraction"])
            shots = {(s.scene_index, s.number): s for s in load_plan(bundle["plan"]).shots}
            by_key = {(f["shot"], f["attempt"]): f for f in bundle["frames"]}
            for label in (e for e in labels if e["script"] == bundle["script"]):
                frame = by_key[(label["shot"], label["attempt"])]
                if args.stored:
                    audit = stored_audit(frame)
                else:
                    png = await store.get(frame["asset"])
                    with Image.open(io.BytesIO(png)) as image:
                        width, height = image.size
                    scene, number = (int(x) for x in label["shot"].split("."))
                    key = (scene - 1, number)
                    rendered = RenderedFrame(key, frame["attempt"], frame["seed"], png, width, height, "")
                    audit = await audit_frame(model, rendered, shots[key], sp, ex)  # type: ignore[arg-type]
                laddered = apply_ladder(audit, ladder)
                withheld = laddered.verdict in (Verdict.FAIL, Verdict.ERROR)
                results.append({**label, "verdict": laddered.verdict.value, "withheld": withheld,
                                 "failed": failed(audit), "models": list(audit.models)})  # fmt: skip
                print(f"{label['script'][:22]:22} {label['shot']:5} a{label['attempt']} {label['label']:5} "
                      f"{'WITHHELD' if withheld else 'shown   '} {','.join(failed(audit)) or '-'}", flush=True)

    # The score.
    print()
    for kind in ("wrong", "right", "weak"):
        group = [r for r in results if r["label"] == kind]
        held = sum(r["withheld"] for r in group)
        word = {"wrong": "caught", "right": "false alarms", "weak": "withheld"}[kind]
        print(f"{kind:5}: {len(group):3} frames, {word} {held}, shown {len(group) - held}")
    by_fault: dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        if r["label"] == "right":
            continue
        for fault in r["faults"]:
            by_fault[fault]["frames"] += 1
            by_fault[fault]["withheld"] += r["withheld"]
            for check in r["failed"]:
                by_fault[fault][check] += 1
    print("\nfault: frames, withheld, the hard checks that failed on them")
    for fault, c in sorted(by_fault.items()):
        checks = ", ".join(f"{k} {v}" for k, v in c.most_common() if k not in ("frames", "withheld"))
        print(f"  {fault:15} {c['frames']:3} {c['withheld']:3}  {checks}")
    print(f"\nladder: {','.join(sorted(c.value for c in ladder)) if ladder is not None else 'all'}; "
          f"{'stored audits' if args.stored else 'models ' + ','.join(sorted({m for r in results for m in r['models']}))}")
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
