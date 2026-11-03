"""T111: the limb agent measured against Katlego's eye labels (limb-agent.md §6, §8, §9).

    cd services/api && python tools/measure_limbs.py LABELS_JSON OUT_JSON [--repeat 2]
    (LABELS_JSON: ../../docs/design/limb-agent/labels.json)

For each labelled drawing: its PNG from Storage, its people (the stored description from
eval/labelled/, or, for a drawing without one, one `describe_frame` call), then LIMB_AGENT_PROMPT
on the vision tier `--repeat` times. Writes nothing to the database or Storage; answers go to
OUT_JSON as they come, so a stopped run resumes where it stopped. Prints the score (§8): the
hunted drawings apart from the rest, recall by framing, hands apart from bodies.
"""

import argparse
import asyncio
import base64
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx2
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm import LLMError, NebiusChatModel, Tier, structured_chat
from app.storage import SupabaseStore
from app.verify.audit import describe_frame

ROOT = Path(__file__).resolve().parents[3]  # the repository

LIMB_AGENT_PROMPT = (  # the 14 Oct prototype's anatomy half, as measured on DeepSeek (§6, verbatim)
    "You look at the people in a storyboard drawing, one by one, and say whether each listed "
    "person's body is drawn as a real human body: anatomy 'defect' only for an error a viewer "
    "would notice at once - two heads, a third arm or leg, a limb growing from the wrong place, "
    "two bodies fused together, a body twisted the way no body bends, a missing head or limb that "
    "should be in view. A limb hidden by the frame's edge, an object, another person or a pose is "
    "not missing. Then the hands: 'deformed' for too many or too few fingers, fused or melted "
    "fingers or a claw-like mass; 'not_visible' when no hand is clear enough to judge. Answer for "
    "every person listed, by their number, and only for them. Before judging the anatomy, count "
    "what is attached to each person's body: heads, arms (shoulder to hand) and legs (hip to "
    "foot), tracing each limb back to the shoulder or hip it grows from. Count a hand or arm only "
    "if it joins this person's body; more than one head, two arms or two legs is a defect."
)

type Defect = Literal[
    "two_heads", "extra_arm", "extra_leg", "misplaced_limb", "fused_bodies",
    "impossible_twist", "missing_head", "missing_limb",
]  # fmt: skip


class BodyAnswer(BaseModel):
    person: int
    heads: int
    arms: int
    legs: int
    anatomy: Literal["normal", "defect", "unclear"]
    defects: list[Defect]
    hands: Literal["fine", "deformed", "not_visible"]


class BodyCheck(BaseModel):
    bodies: list[BodyAnswer]


@dataclass(frozen=True)
class Label:
    asset: str
    source: str  # labelled-109 | probe-14oct | hunt
    verdict: str  # normal | defect | unclear
    faults: tuple[str, ...]
    framing: str | None


@dataclass(frozen=True)
class Ask:
    ok: bool
    named: bool  # the answer names a body defect for some listed person
    hands: bool  # the answer calls some listed person's hands deformed


@dataclass(frozen=True)
class Drawing:
    people: int
    asks: tuple[Ask, ...]


@dataclass
class Score:
    asks: int = 0
    errors: int = 0
    defect_asks: int = 0
    caught: int = 0
    normal_asks: int = 0
    alarms: int = 0
    compared: int = 0
    agreed: int = 0
    not_asked: int = 0
    hands_asks: int = 0
    hands_caught: int = 0
    hands_normal_asks: int = 0
    hands_alarms: int = 0

    def line(self) -> str:
        def pct(n: int, d: int) -> str:
            return f"{n}/{d} = {100 * n / d:.1f}%" if d else "-"

        return (
            f"recall {pct(self.caught, self.defect_asks)}; "
            f"false alarms {pct(self.alarms, self.normal_asks)}; "
            f"agreement {pct(self.agreed, self.compared)}; errors {pct(self.errors, self.asks)}; "
            f"not asked {self.not_asked}; hands: recall {pct(self.hands_caught, self.hands_asks)}, "
            f"false alarms {pct(self.hands_alarms, self.hands_normal_asks)}"
        )


def _framing(framing: str | None) -> str | None:
    return None if framing is None else framing.removesuffix(" (describer)")


def score(labels: Sequence[Label], answers: Mapping[str, Drawing], repeat: int) -> dict[str, Score]:
    """§8, per drawing and ask: recall on body defects, false alarms on normal drawings, agreement
    between asks, errors; hands apart; `hunt` apart from `base`, and `base` by framing. A drawing
    with no described people is never asked: a defect there is missed on every ask."""
    out: dict[str, Score] = {"base": Score(), "hunt": Score()}
    for lab in labels:
        if lab.verdict not in ("defect", "normal") or lab.asset not in answers:
            continue
        drawing = answers[lab.asset]
        hands_only = (
            lab.verdict == "defect" and bool(lab.faults) and set(lab.faults) == {"deformed_hands"}
        )
        body_defect = lab.verdict == "defect" and not hands_only
        group = "hunt" if lab.source == "hunt" else "base"
        keys = [group]
        if group == "base" and _framing(lab.framing) is not None:
            keys.append(f"framing:{_framing(lab.framing)}")
        for key in keys:
            s = out.setdefault(key, Score())
            if drawing.people == 0:
                s.not_asked += 1
                if body_defect:
                    s.defect_asks += repeat
                continue
            good = [a for a in drawing.asks if a.ok]
            s.asks += len(drawing.asks)
            s.errors += len(drawing.asks) - len(good)
            if body_defect:
                s.defect_asks += len(good)
                s.caught += sum(a.named for a in good)
            elif lab.verdict == "normal":
                s.normal_asks += len(good)
                s.alarms += sum(a.named for a in good)
            if "deformed_hands" in lab.faults:
                s.hands_asks += len(good)
                s.hands_caught += sum(a.hands for a in good)
            elif lab.verdict == "normal":
                s.hands_normal_asks += len(good)
                s.hands_alarms += sum(a.hands for a in good)
            if len(good) >= 2:
                s.compared += 1
                s.agreed += len({a.named for a in good}) == 1
    return out


def _stored_people(root: Path) -> dict[str, list[dict[str, str]]]:
    """asset -> the stored description's people, from Tumo's labelled bundles."""
    out: dict[str, list[dict[str, str]]] = {}
    for bundle in sorted((root / "eval" / "labelled").glob("*.json")):
        frames: list[dict[str, Any]] = json.loads(bundle.read_text())["frames"]
        for frame in frames:
            audit: dict[str, Any] = frame.get("stored_audit") or {}
            description: dict[str, Any] | None = audit.get("description")
            if description is not None:
                people: list[dict[str, str]] = description["people"]
                out[frame["asset"]] = [
                    {"position": p["position"], "appearance": p["appearance"]} for p in people
                ]
    return out


async def _ask(
    model: NebiusChatModel, png: bytes, people: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    lines = [f"{i}: {p['position']} third, {p['appearance']}" for i, p in enumerate(people)]
    image = f"data:image/png;base64,{base64.b64encode(png).decode()}"
    messages = [
        {"role": "system", "content": LIMB_AGENT_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "\n".join(["People in the drawing:", *lines])},
            {"type": "image_url", "image_url": {"url": image}},
        ]},
    ]  # fmt: skip
    try:
        result = await structured_chat(model, messages, BodyCheck, Tier.VISION, max_tokens=4096)
    except (LLMError, ValidationError) as exc:
        return {"ok": False, "error": str(exc) if isinstance(exc, LLMError) else type(exc).__name__}
    listed = [b for b in result.value.bodies if 0 <= b.person < len(people)]
    usage = result.chat.usage
    return {
        "ok": True,
        "named": any(b.anatomy == "defect" or b.defects for b in listed),
        "hands": any(b.hands == "deformed" for b in listed),
        "bodies": [b.model_dump() for b in result.value.bodies],
        "tokens": [usage.prompt_tokens, usage.completion_tokens],
        "model": result.chat.model,
    }


def _usage(records: Iterable[Mapping[str, Any]]) -> str:
    """The run's tokens: the asks, and the descriptions of drawings that had none stored."""
    asks: list[list[int]] = [a["tokens"] for r in records for a in r["asks"] if a.get("ok")]
    described: list[list[int]] = [r["describe_tokens"] for r in records if r["describe_tokens"]]
    return (
        f"asks {len(asks)}: {sum(t[0] for t in asks)} prompt + {sum(t[1] for t in asks)} "
        f"completion tokens; descriptions {len(described)}: {sum(t[0] for t in described)} + "
        f"{sum(t[1] for t in described)}"
    )


def _rows(path: Path) -> list[dict[str, Any]]:
    """The labels file's rows."""
    return json.loads(path.read_text())["labels"]


def _answers(path: Path) -> dict[str, Any]:
    """The answers a stopped run already has."""
    return json.loads(path.read_text())["answers"] if path.exists() else {}


def _drawing(record: Mapping[str, Any]) -> Drawing:
    asks = tuple(Ask(a["ok"], a.get("named", False), a.get("hands", False)) for a in record["asks"])
    return Drawing(record["people"], asks)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    stored = await asyncio.to_thread(_stored_people, ROOT)
    rows = await asyncio.to_thread(_rows, args.labels)
    labels = [
        Label(
            r["asset"],
            r["source"],
            r["verdict"],
            tuple(f["defect"] for f in r["faults"]),
            r["framing"],
        )
        for r in rows
    ]
    records: dict[str, Any] = await asyncio.to_thread(_answers, args.out)
    settings = Settings()
    model = NebiusChatModel.from_settings(settings)
    print(
        f"vision model {settings.nebius_model_vision}, thinking {settings.nebius_vision_thinking}",
        flush=True,
    )
    lock = asyncio.Lock()
    gate = asyncio.Semaphore(args.concurrency)

    def save() -> None:
        scores = score(
            labels,
            {
                k: _drawing(v)
                for k, v in records.items()
                if len(v["asks"]) >= args.repeat or v["people"] == 0
            },
            args.repeat,
        )
        args.out.write_text(
            json.dumps(
                {"answers": records, "score": {k: vars(s) for k, s in scores.items()}}, indent=1
            )
        )

    async with httpx2.AsyncClient(timeout=120) as client:
        store = SupabaseStore(url=settings.supabase_url, secret_key=settings.supabase_secret_key,
                              bucket=settings.supabase_storage_bucket, client=client)  # fmt: skip

        async def one(lab: Label) -> None:
            if lab.verdict == "unclear":
                return  # left out of every score (§8): asking would only spend tokens
            record: dict[str, Any] | None = records.get(lab.asset)
            if record is not None and (record["people"] == 0 or len(record["asks"]) >= args.repeat):
                return
            async with gate:
                png = await store.get(lab.asset)
                if record is None:
                    people: list[dict[str, str]] | None = stored.get(lab.asset)
                    described = people is None
                    describe_tokens: list[int] = []
                    if people is None:
                        try:
                            description, chat = await describe_frame(model, png)
                        except (LLMError, ValidationError) as exc:
                            print(f"describe failed on {lab.asset}: {exc}", flush=True)
                            return
                        people = [
                            {"position": p.position, "appearance": p.appearance}
                            for p in description.people
                        ]
                        describe_tokens = [chat.usage.prompt_tokens, chat.usage.completion_tokens]
                    record = {"people": len(people), "listed": people, "described": described,
                              "describe_tokens": describe_tokens, "asks": []}  # fmt: skip
                while record["people"] and len(record["asks"]) < args.repeat:
                    record["asks"].append(await _ask(model, png, record["listed"]))
            async with lock:
                records[lab.asset] = record
                save()
                done = sum(
                    1 for v in records.values() if v["people"] == 0 or len(v["asks"]) >= args.repeat
                )
                calls = [a.get("named") for a in record["asks"]]
                print(f"{done}/{len(labels)} {lab.source} {lab.verdict}: {calls}", flush=True)

        await asyncio.gather(*(one(lab) for lab in labels))
    await model.aclose()
    save()
    final = score(labels, {k: _drawing(v) for k, v in records.items()}, args.repeat)
    for key in sorted(final):
        print(f"{key}: {final[key].line()}")
    print(_usage(records.values()))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
