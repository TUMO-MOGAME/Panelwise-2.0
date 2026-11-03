# Devpost — "About the project" (draft)

> Working copy of the Devpost story. Paste **everything below the line** into Devpost.
>
> Before submitting (T034/T035): every `⟨TBD⟩` is either filled with a measured number or cut, the
> Inspiration paragraph is rewritten in our own words, and every claim is checked against what the
> demo actually does. FrameFlow figures come from FrameFlow's STATUS.md; the ~6% recall is an upper
> bound computed from those counts (FrameFlow lists both 202 and 170 locations; we use the lower).

**Elevator pitch** (Devpost's own field, not part of the story below; chosen 2026-10-29 by Katlego):

> Panelwise turns a screenplay into a storyboard and a comic book. NVIDIA Nemotron checks every
> frame against the script, so nothing appears that the writer didn't write.

**Thumbnail and gallery** (3:2; made 2026-10-29, not committed): the thumbnail sets the-red-kite's
scene 3 lines beside shot 3.1, drawn on the hosted stack on 20 Oct (audit: pass); the gallery is
screenshots of the hosted app and pages from its storyboard and comic PDFs.

---

## Inspiration

A storyboard is how a director shows everyone what the film will look like before a single day is
shot. For small productions (a student film, a community play, a short shot on a phone) it is
usually the first thing cut: it takes an artist, time and money that nobody has. We had already
built **FrameFlow**, a pre-production assistant that reads a screenplay and breaks it down into
characters, locations and shots. But a list of shots is still not a picture. We wanted to *draw*
them, and once the frames existed, the same script could become a comic book, with its own
dialogue in the speech bubbles.

Our first renders showed us the real problem: image models invent. They add a third person to a
two-person scene, a prop the script never mentions, the wrong character in the wrong place. For a
storyboard that is worse than no picture at all, because it tells the crew something the writer
never wrote. So Panelwise is built around one rule:
**no panel may show a character, prop, line or event that is not in the screenplay.** A second
model looks at every frame, checks it against the script and redraws it when they disagree.

We also wrote our test scripts about the places we know: load-shedding, a gogo's recipe, market
day, a borrowed bicycle. A tool that only works on the examples it was tuned on is not one we
would trust, so we measured Panelwise on scripts it had never seen.

## What it does

Upload a screenplay. Panelwise parses it into scenes and dialogue, extracts the characters and
locations with **NVIDIA Nemotron on Nebius Token Factory**, plans a shot list, renders one frame per
shot, and lays the frames out as storyboard pages or as comic pages with speech bubbles taken from
the script's dialogue. Every panel links back to the verbatim lines it came from.

Every rendered frame is audited, in two steps: **Nemotron 3.5 Super VL** describes the frame
without seeing the script — who is in it, the framing, the time of day — and **Nemotron Super
compares that description with the shot spec** and sends the frame back for a re-render when they
disagree. The description and the verdict are both
logged, so you can see why a frame was accepted.

## How we built it

- **Grounded extraction.** The screenplay is split on scene boundaries and each chunk goes to
  Nemotron with a strict JSON schema. Every extracted entity must carry a verbatim quote from the
  script; a grounding filter drops anything whose quote can't be found in the source.
- **Model tiers.** Every model call goes through one client with two text tiers: the fast tier,
  **Nemotron 3.5 Lightning** with thinking switched off, and **Nemotron 3 Super** with thinking on
  for judgement calls. Every result records which model answered and how many tokens it spent
  thinking. High-volume, schema-bound work (extraction, shot planning) goes on the fast tier.
- **Rendering.** **FLUX.2 [klein]** on fal.ai draws each frame, since Token Factory serves no
  image model. A character's look comes from the script's own words, written
  into every frame prompt they appear in.
- **The audit loop.** Each frame may be rendered at most \(k+1\) times. If a single render passes
  the audit with probability \(p\), the expected number of renders per frame is

  $$\mathbb{E}[N] \;=\; \sum_{i=0}^{k} (1-p)^i \;=\; \frac{1-(1-p)^{k+1}}{p},$$

  which is how we budget renders: with \(k = 2\) (a first render and two re-renders) and
  \(p \approx 0.97\) (37 of 38 shots accepted at their first drawing on two held-out scripts, 17 Oct,
  under the hosted rule ladder), a frame costs about \(1.03\) renders on average.
- **Stack.** A Next.js app on Vercel in front of a FastAPI service on Render, with Supabase for
  Postgres, image storage and sign-in, live since 16 Oct at https://panelwise.vercel.app.

## Challenges we ran into

**Measuring the right thing.** In FrameFlow we tracked a *faithfulness* score — the share of
extracted entities that really appear in the script:

$$F = \frac{|E_{\text{grounded}}|}{|E|}.$$

After prompt tuning we hit \(F = 1.0\) (15 of 15 grounded), and it looked like we were done. We
weren't. Faithfulness is precision; it says nothing about what was *missed*. The same screenplay
has 77 speaking characters and at least 170 distinct locations, so the recall of that run was at
most

$$R = \frac{|E \cap G|}{|G|} \;\le\; \frac{15}{77 + 170} \approx 6\%.$$

A perfect score on a sixth of the cast is a failure. Now we report precision and recall together,
and only on a full parse.

**Measuring on a fragment — twice.** An earlier score of 0.778 turned out to be computed on a PDF
parse that silently dropped about two-thirds of the screenplay. We threw the number away and
switched parsers.

**Infrastructure walls.** Chunked extraction needs 17 requests per feature-length script. A free
API tier capped at 20 requests a day died at chunk 7 of 17, and a local 3B model timed out on a
single 20K-character chunk. On Nebius Token Factory a full-script run is finally cheap enough to
finish: at catalog prices, an estimated 0.3M tokens in and 0.15M out per screenplay comes to about

$$0.3 \times \$0.06 + 0.15 \times \$0.24 \approx \$0.05 .$$

Measured (16 Oct, the-red-kite, storyboard and comic on the deployed stack): it finished, with 44
drawings (about $0.13–0.18 at fal's $0.003–0.004 each) and about 0.34M tokens (about $0.15 on Token
Factory, at most $0.19: the audit runs on Nemotron Super and Super VL, not only Lightning), roughly
$0.30 a script end to end.

**Errors that lied.** In FrameFlow, when one provider in the fallback chain hit its quota, the chain
fell through to a local endpoint that wasn't running and reported only that last error — a 404
from `localhost:11434` — pointing us at Ollama when the cause was the quota. FrameFlow's chain now
reports every provider's failure; Panelwise has no chain at all. It calls one provider, so the
error names the model that failed.

**Reading the catalog versus measuring the API.** Before writing any code we spent under half a cent
probing Token Factory, and several answers contradicted what the documentation suggested:

- The model catalog lists no JSON mode for any Nemotron model, yet strict `json_schema` output
  **was enforced**, even when the prompt never mentioned the schema. The looser `json_object` mode
  returned JSON in the wrong shape, and in one run it added a detail the scene never gave — a
  character "likely a lighthouse keeper". That is exactly the kind of invention grounding has to
  catch.
- Nemotron reasons by default. For a one-number answer, thinking took Lightning from 4 output
  tokens to 271. Only two of the four switches we tried actually turned it off.
- No Nemotron model on Token Factory accepted images, so the frame audit had to be redesigned
  around a vision model that describes and a Nemotron model that judges. When Nemotron 3.5 Super VL
  arrived on Token Factory, we measured it on the same stored drawings before switching the
  describe step to it on 17 Oct.

## Accomplishments that we're proud of

- Across 15 live runs on three self-written screenplays (5 each), **no ungrounded quote or shot
  citation survived into the shot plan**: every kept quote and every shot's cited text was re-checked
  in code against the script lines it names, and all 15 runs came back at 0. Every action paragraph
  and speech landed in exactly one shot, in every run. (That is the text side; whether a rendered
  image shows only what the shot says is the frame audit's job, measured below.)
- Nemotron 3.5 Lightning's own proposals were 89.8% faithful (246 of 274 entities fully grounded);
  the filter dropped what didn't ground (the unlocated quotes, or the whole entity). It found 85 of
  the 90 speaking-character appearances itself; the only miss was the same one in each run of
  the largest script, a station announcer heard in voice-over, whom the script's dialogue cues
  supply. Numbers and method:
  [`eval/`](https://github.com/Katlego-tech/Panelwise/blob/main/eval/README.md).

- **The frame audit, scored against our own eyes.** On 109 drawn frames we labelled by hand, picked
  for their faults (re-scored 20 Oct on Nemotron 3.5 Super VL with the hosted rule ladder), the audit
  holds back **38 of 57 wrong frames (67%)** and only **1 of 40 right ones**; all 12 weak frames are
  shown with their notes. Method and every frame:
  [`eval/measurements/t124/`](https://github.com/Katlego-tech/Panelwise/blob/main/eval/measurements/t124/README.md).

## What we learned

- A metric you can't break down is a metric you can't trust. A perfect precision score hid the fact
  that we were missing at least 94% of what was in the script.
- Grounding has to be enforced *after* generation, in code, not asked for in the prompt. Models agree
  to "only use what's in the script" and then don't.
- Vision models make good critics of image models: checking a frame against a spec is far easier
  than generating it correctly the first time. Ours holds back two in three wrong frames while
  wrongly holding back one right frame in forty; its biggest gap is the judge not recognising a
  drawn character, which is why a person drawn twice still only warns.

## What's next for Panelwise

Editable panels (redraw a single frame with a note), animatics with scratch audio, and exporting
shot lists straight into scheduling tools.
