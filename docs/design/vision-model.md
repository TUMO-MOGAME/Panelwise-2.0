# Design — `verify` the vision model: Nemotron 3.5 Super VL as the describer

**Status:** built and live (T105: #191 design, #192 code; Super VL with thinking off is every vision call since 2026-10-17; T106 and T107 adapted the describer on 18 Oct) · **Owner:** Katlego (Claude) · **Tasks:** T105 · **Spec:** [SPEC.md](../../SPEC.md) US2 (frame audit)
· **Raised:** 2026-10-17 by Katlego, after NVIDIA's 15 Oct release ([nebius-findings.md § U8](../nebius-findings.md#u8--an-nvidia-vision-model-2026-10-17))
· **Decided 2026-10-17 by Katlego: Super VL is the target vision model.** Nemotron is the sponsor's
technology; DeepSeek-V4.1-Flash, another vendor's model, was only ever the stand-in option A had to
settle for. So T105 doesn't ask whether Super VL beats DeepSeek on a pipeline tuned to DeepSeek; it
asks whether Super VL **fits** (§8) and **how much of the audit translates** to it, and the parts
that don't are adapted to Super VL

---

## 1. What this covers

Which model answers the audit's **vision** calls, and how we decide. Every call on `Tier.VISION`
uses one model, `NEBIUS_MODEL_VISION`: the describer (`FrameDescription`), the sex agent
(`PersonCheck`, T095) and the presence agent (`Presence`, T099). The same holds for the open agents
(T102's questions, T104's layout, T097's heads) and for any later one (limbs, bubbles). Since
2026-10-17 that model is `nvidia/Nemotron-3.5-Super-VL`, thinking off (T105). Until then it was
`deepseek-ai/DeepSeek-V4.1-Flash`, because until 12 Oct Token Factory served no NVIDIA model that
takes images (findings § U7). T105 measured Super VL on drawings we already had: whether it fits,
and which parts of the audit (prompts, schemas, checks, agents) carry over as they are and which
need adapting to it (§8).

**Not covered:** the judge (`Tier.REASONING`, Nemotron Super, unchanged); the prompts, schemas,
checks and the rule ladder (verify.md, unchanged: a model swap that needs a prompt change is a
finding, recorded and decided separately, not folded in here); the image renderer (fal.ai,
storyboard.md §3.5).

## 2. Reference material

| Kind | Where |
| --- | --- |
| Why the describer isn't NVIDIA today | [nebius-findings.md](../nebius-findings.md) § U7, § U7 re-check, § The vision decision (option A now, option B "an NVIDIA model that sees the frame" as a stretch) |
| The new model, checked | nebius-findings.md § U8: the catalog row, the price, and the one probe (a comic page read correctly; 367 of 395 completion tokens thinking) |
| The vision calls | `services/api/app/verify/audit.py`: `describe_frame` (`FrameDescription`, `max_tokens=4096`), the sex agent (`PersonCheck`, 1024), `find_character` (`Presence`, 4096) |
| The tier and its thinking default | `services/api/app/llm/client.py`: `Tier.VISION`, `_THINKING_DEFAULT[Tier.VISION] = None` (nothing sent, because the toggle was measured only on Nemotron, findings § U2) |
| Structured output | `services/api/app/llm/structured.py` `structured_chat`: strict `json_schema` plus the schema in the prompt, one repair retry |
| The measuring tool | `python -m app.verify.reaudit <project-id> [--target] [--limit]` (T071, verify.md §6): today's audit on stored drawings; it writes nothing and draws nothing, so the only spend is Token Factory's |
| Stored drawings | local `frame_audits` with their PNGs in the `panelwise-dev` bucket. Katlego's machine: the-red-kite project `28a0476c…` (44 attempts, 2026-10-16). Tumo's machine: the held-out runs in `eval/runs/` |

## 3. Domain model

No new entity, table or migration. One setting:

- `NEBIUS_VISION_THINKING` (`Settings.nebius_vision_thinking: bool | None`): the thinking toggle
  sent on `Tier.VISION` calls. **Default `false` since T105** (`config.py`), so every vision call
  sends `chat_template_kwargs: {"enable_thinking": false}`; `true` sends `true`. **Blank → `None` →
  nothing sent** (the default before T105, so DeepSeek's calls were byte for byte unchanged). A
  caller's explicit `thinking=` still wins, as on the other tiers.

`NEBIUS_MODEL_VISION` already exists. T105 changed its **default** on 2026-10-17, after the
measurement, and `NEBIUS_VISION_THINKING`'s with it (findings § U8).

## 4. Flow

The audit's flow is unchanged (verify.md §4); only the vision tier's model and thinking toggle
change. The measurement:

```mermaid
sequenceDiagram
    participant K as Katlego / Tumo
    participant R as reaudit (CLI)
    participant D as local Postgres + panelwise-dev bucket
    participant T as Token Factory
    K->>R: NEBIUS_MODEL_VISION=<model> NEBIUS_VISION_THINKING=<on/off/unset> reaudit <project>
    R->>D: every logged attempt and its PNG
    loop each attempt
        R->>T: describe (vision), judge (Nemotron), sex/presence agents (vision)
        T-->>R: description, judgement, answers, usage
    end
    R-->>K: one line per attempt: stored verdict → new verdict, hard checks; a summary
    K->>K: look at every attempt whose verdict differs between the two models
```

**Runs:** the same project(s) with (1) DeepSeek-V4.1-Flash, unset thinking (today's baseline,
re-run so both sides are judged by today's code); (2) Super VL, thinking unset (its default, on);
(3) Super VL, `NEBIUS_VISION_THINKING=false`. Logging is at INFO, so each call's model and usage are
in the log. Tokens and seconds per attempt come from there.

**Failure paths:**
- Super VL rejects `response_format` or ignores the schema → `structured_chat` repairs once, then
  `ValidationError` → that audit is `ERROR`, the same as any failed call today. The measurement
  counts these; §8's bar caps them.
- Thinking on spends `max_tokens` with no content → `LLMEmptyResponse` (billed and counted, T069) →
  `ERROR`. Counted the same way. It is the reason run (3) exists.
- Token Factory 429 or 5xx → the client's retries (T004), unchanged.
- **Nothing here touches the hosted demo** until the default changes in a merged PR. Render then
  redeploys the API on that push (`services/api/**`), and the next audit uses the new model.

## 6. Contracts

```python
# app/core/config.py
nebius_vision_thinking: bool | None = False  # NEBIUS_VISION_THINKING; False since T105 (None before); blank: None, nothing sent
#   joins _blank_is_off's field list, so "NEBIUS_VISION_THINKING=" in .env means None, not an error

# app/llm/client.py
class NebiusChatModel:
    def __init__(self, *, ..., vision_thinking: bool | None = None, ...) -> None: ...
    #   the thinking default for Tier.VISION; FAST and REASONING keep _THINKING_DEFAULT's values
    @classmethod
    def from_settings(cls, settings: Settings) -> Self: ...   # passes settings.nebius_vision_thinking
    async def chat(self, messages, tier=Tier.FAST, *, thinking: bool | None = None, ...) -> ChatResult: ...
    #   think = thinking if thinking is not None else (self._vision_thinking if tier is Tier.VISION
    #           else _THINKING_DEFAULT[tier]); None sends no chat_template_kwargs (unchanged)
```

```bash
# .env.example (beside NEBIUS_MODEL_VISION)
# The vision model's thinking toggle (docs/design/vision-model.md, T105): blank sends nothing.
NEBIUS_VISION_THINKING=false   # since T105's defaults; blank before
```

**If and only if §8's bar is met**, the same PR (or a follow-up, the measurement recorded first)
changes `nebius_model_vision`'s default to `"nvidia/Nemotron-3.5-Super-VL"` and
`nebius_vision_thinking`'s to the measured setting. `.env.example`, nebius-findings.md § Settled
configuration, and verify.md §2's "The vision decision" row change with it. `render.yaml` needs
nothing: the hosted API takes the code defaults.

## 7. Structure

| Path | New? | Responsibility |
| --- | --- | --- |
| `services/api/app/core/config.py` | changed | `nebius_vision_thinking`; in `_blank_is_off`'s list; later, the two defaults |
| `services/api/app/llm/client.py` | changed | `vision_thinking`, used as `Tier.VISION`'s default |
| `services/api/tests/llm/test_client.py` | changed | §9's tests |
| `.env.example` | changed | `NEBIUS_VISION_THINKING=` |
| `docs/nebius-findings.md` | changed | § U8: the measurement's table and the verdict; § Settled configuration if adopted |
| `docs/design/verify.md` | changed, if adopted | §2's vision-decision row names the model |
| `README.md`, `SPEC.md`, `docs/submission/about.md` | changed, if adopted | "a vision model describes each frame" becomes "Nemotron 3.5 Super VL describes each frame", in their own PR |

## 8. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| How to decide | measure first, on stored drawings with `reaudit` (no drawings, a few cents) | swap the default and watch: the hosted demo's frames would be the experiment, and a worse describer shows a judge wrong frames; trust NVIDIA's benchmark (a vendor claim, and not our task) |
| What decides (Katlego, 2026-10-17) | **Super VL is the target; the measurement shows fit and translation.** **Fit:** (1) `ERROR`s (schema or empty) at most 2% of attempts; (2) tokens per attempt at most 1.2× DeepSeek's (the 2.8M monthly cap, deploy.md §6); (3) seconds per attempt at most 1.5× DeepSeek's (a judge waits on the storyboard); (4) every attempt whose hard checks differ is looked at, and no wrong frame is shown that DeepSeek withheld. **Translation:** per part of the audit (structured output, the description's fields, the judge's matches, each agent, each check), the share that agrees with today's, and for each part that doesn't, a follow-up task that adapts it to Super VL | "adopt only if it beats DeepSeek" (the first draft of this row): the pipeline's prompts and checks were tuned on DeepSeek since 2026-09-30, so a comparison flatters it; and the sponsor alignment, an NVIDIA model for every model call, is the reason for the change, so tuning to Super VL is expected work, not a cost against it |
| Thinking on the vision tier | a setting, measured both ways | hard-code on or off: measured only on Nemotron's text models (U2); the probe shows Super VL thinks by default (367 of 395 tokens), which may cost more than it helps for description |
| One model for every vision call | yes: the describer and every agent share `Tier.VISION` | a model per agent: more settings and more measurement, for agents whose prompts were tuned on DeepSeek anyway; can come later, per agent, if the measurement shows one agent worse |
| Bolt 74B-A9B / Bolt E4B | not considered | not on Token Factory; our runtime calls must be Token Factory's (the hackathon rule, deploy.md §1) |

Deviations from [docs/architecture-defaults.md](../architecture-defaults.md): none.

## 9. How this is verified

**Tests first** (`tests/llm/test_client.py`, no network):
- unset `vision_thinking`: a `Tier.VISION` call sends no `chat_template_kwargs` (the existing
  `test_vision_tier_sends_no_thinking_toggle_by_default` stays green, unchanged);
- `vision_thinking=False`: a vision call sends `{"enable_thinking": false}`; FAST and REASONING
  calls are unchanged;
- an explicit `thinking=True` on a vision call overrides `vision_thinking=False`;
- `from_settings` passes `nebius_vision_thinking`; `NEBIUS_VISION_THINKING=` (blank) is `None`;
- `bash scripts/gate.sh` green.

**The measurement** (Token Factory spend, about $0.15 a run of the-red-kite's 44 attempts;
Katlego's go-ahead before each batch):
- the three runs of §4 on the-red-kite (Katlego's machine) and, if Tumo runs them, two held-out
  projects on his;
- recorded in nebius-findings.md § U8 as one table per project: attempts, verdicts per model,
  attempts that differ, and, for each that differs, which model was right (looked at, with the frame
  named); `ERROR`s; prompt, completion and reasoning tokens per attempt; seconds per attempt;
- the fit against §8, the translation table, and a follow-up task for each part that needs
  adapting; then the defaults change (Katlego and Tumo).

## 10. Open questions

- [x] **Does Super VL honour strict `json_schema`?** `supported_features` doesn't list
  `structured_outputs` (nor does DeepSeek's, which honours it). The first run answers this.
  **Yes:** 44 of 44 on the-red-kite, 0 repairs; 25 of 26 on the-lighthouse-inspector (8.1 looped:
  T109) (nebius-findings.md § U8 measured, § U8 held out).
- [x] **Image tokens per frame.** The probe's page cost 3,314 image tokens. A 1280 × 720 frame's
  count on each model decides (3) of §8's bar more than the text does. **Answered by the bar
  itself:** 0.95× DeepSeek's tokens and 1.43× its median time per attempt (findings § U8).
- [x] **Which held-out projects** Tumo can re-audit on his machine (`eval/runs/`), so the bar isn't
  judged on the-red-kite alone, the script the prompts were developed on. **The-lighthouse-inspector**
  (findings § U8 held out), and the 109 labelled frames across 11 scripts (§ U8 on the labelled
  frames; eval/audit-mistakes.md).
- [x] If adopted, whether the pitch line changes to "Nemotron sees and judges every frame": it
  would, but that is the team's wording, decided with the README (T033). **Decided:** "Nemotron 3.5
  Super VL describes each frame; Nemotron Super judges it against the script." (SPEC.md).
