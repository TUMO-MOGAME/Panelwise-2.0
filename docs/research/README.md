# Research

Background reading the team brought in, and what each one changes in our work. These are compiled
research reports, not peer-reviewed papers: each cites web pages and papers by number. **A figure
from them is a lead, not a fact.** Check the primary source (the arXiv paper, the letterer's own
guide) before a design doc relies on it or the pitch quotes it.

| File | Added | Applies to |
|---|---|---|
| [speech-bubble-placement.pdf](speech-bubble-placement.pdf): *The Architecture of Sequential Reading: Visual Syntax, Compositional Dynamics, and Dialogue Engineering in Comic Book Lettering* (10 pp.) | 2026-10-18, Katlego | `comic`: T098, T112, T114 ([comic.md](../design/comic.md) §4 steps 7–8, §10) |
| [§ Same-speaker balloons](#same-speaker-balloons): notes on one speaker's several balloons (no PDF; kept here in full) | 2026-10-18, Katlego | `comic`: T118, and comic.md §10 |
| [anatomical-fidelity.pdf](anatomical-fidelity.pdf): *Anatomical Fidelity in Latent Diffusion and Flow Models: Architectural, Conditioning, and Post-Hoc Mechanisms for Digit and Limb Rectification* (15 pp.) | 2026-10-18, Katlego | `verify`: T111 the limb agent ([limb-agent.md](../design/limb-agent.md)) |

## Speech bubble placement

What it says, against what we do (comic.md §4 steps 7–8):

| The report says | We do | Where it goes |
|---|---|---|
| The tail aims at the speaker's **mouth**, as if a line ran on from its tip to the face (§3, from Evan Waterman's lettering guide) | T114 aims at the centre of the head box's lower third, stopping at the grown head rect (was T098's nearest point of the head box) | **T114** (Katlego, 2026-10-18): done |
| The tail stops at about 50–60% of the way from the balloon to the head, never touching the figure (§3, the tail table) | stops 12 px outside the head box (T098's `HEAD_MARGIN`) | comic.md §10: a shorter tail is a later choice, judged by eye |
| Tails never cross one another (§3, from Graphixly) | T112 | done |
| A tail never crosses another character's face, throat or line of sight (§3) | T116: no tail across another head rect | done for faces; throat and sightline aren't known |
| Faces are never covered (§2) | T098: a box over any head costs 2.0 | done; soft, as designed |
| Hands doing something stay visible (§2) | not known: no check sees hands | not planned: T111 wasn't adopted (findings § U9), so no check gives hand boxes |
| The tail leaves the balloon near its middle, not its far edge (§3, from Blambot) | from the point of the box, shrunk by its corner radius, nearest the tip | comic.md §10 |
| The first speaker sits left; when the art has them right, link balloons or re-stage (§3) | the reading order is hard (T023); T112 keeps tails from crossing | no change: we can't re-stage a drawn frame |
| 20–25 words a balloon, 35 a panel; a long speech is split into linked balloons at its breaks (§3, §5) | one balloon per dialogue element, never cut (Non-negotiable I) | comic.md §10: splitting at sentence ends keeps every word, in order |
| Lines stacked as an oval (short, long, short), not a block (§3) | greedy wrap, centred | comic.md §10 |
| Balloons can butt against the panel border (§2) | 16 px inset | no change |

## Same-speaker balloons

Notes Katlego added on 2026-10-18 on how letterers handle several balloons from one speaker. They
came without their sources, so check a claim against a letterer's own guide (Blambot, Todd Klein,
Comicraft) before the pitch quotes it. First the notes, then what they mean for us.

### The notes

**Why one speech is split.**
- **Word counts:** about 20–25 words a balloon, to keep about two thirds of the panel for the art
  and one third for the words.
- **Rhythm:** a split reads as a breath, a hesitation or a turn in the thought, without extra
  ellipses or narration.

**Three ways to join one speaker's consecutive balloons**, each with its own pacing:

| Join | Drawn as | Reads as |
|---|---|---|
| **Abutted** (fused, merged) | the balloons touch, sharing a flattened seam or an open neck inside one continuous outline | rapid speech, one thought rolling into the next with no breath |
| **Bridged** (connector) | separate balloons near each other, joined by a short narrow channel in the outline's stroke; straight, direct and as short as possible | a slight pause: a comma's beat, a small change of cadence |
| **Unlinked** | separate balloons with space between, in reading order (top left to bottom right) | a deliberate pause, a dramatic beat, a silence |

**Tails.**
- **One tail for joined balloons:** abutted or bridged balloons share one tail. It leaves the
  balloon **closest to the speaker's head** and aims at the mouth; the join says the rest is the
  same voice.
- **A tail each for unlinked balloons:** each one gets its own short tail back to the speaker's
  face.
- **No crossings:** one speaker's tails never cross each other, another character's throat or
  face, or an intervening character's line of sight.

**Interleaved dialogue** (speaker A, then B, then A in one panel).
- **Staircase:** the balloons step down the reading path: A top left, B middle or right, A lower
  centre or left.
- **No join across B:** A's two balloons are never joined, since a connector can't run behind or
  over B's balloon or tail. A's second balloon is unlinked, with its own tail.
- **Split the panel:** if A → B → A in one panel would cross tails or crowd the figures, the
  exchange is split over two panels.

**What writers mark in a comic script.**
- **`//` inside one speech:** marks where the letterer splits it into balloons ("You have clearly
  never met my grandmother. // Or heard the story about the eel trap.").
- **`(LINKED)` or `(JOINED)`:** the speaker listed twice in a row, with `(LINKED)` on the second
  block, asks for joined balloons. Without it, the writer means a real pause and separate balloons.

### What it means for us

| The notes say | We do | Where it goes |
|---|---|---|
| Joined balloons share one tail | T118: a chain has one tail | done |
| The tail leaves the balloon **closest to the head** | T119: the tail is on the linked box nearest the speaker (was the chain's **first** balloon, T118) | done |
| Bridges are short, straight, stroke-width channels | T118: a straight 22 px neck, at most 120 px | done; the width is a look to judge, and 22 px is wider than a stroke on purpose (it reads as the balloon stretching, Katlego's ask) |
| Abutted balloons for rapid speech | T120: two linked boxes under 16 px apart merge into one outline | done |
| Unlinked for a deliberate pause; a tail each | T121: a `(beat)` or `(pause)` parenthetical on the second line unlinks; an action line between does not (built, then dropped 2026-10-18: it unlinked almost every pair) | done |
| No join across another speaker (A → B → A) | T118 links only consecutive lines, so A's two lines stay unlinked with a tail each | done |
| No tail across another face or sightline | T116: faces (head rects) | done for faces; sightlines aren't known (no gaze direction in the audit) |
| Split an A → B → A panel that can't fit | one panel per shot (comic.md §3) | no change: the shot planner, not lettering, decides panels |
| 20–25 words a balloon; split at the breaths | one balloon per dialogue element, never cut | comic.md §10: split a long speech at sentence ends into linked balloons, every word kept in order (Non-negotiable I) |
| `//` splits, `(LINKED)` joins | not read | a screenplay doesn't use them; a `//` in dialogue is lettered as written today. If scripts written for Panelwise use them, `//` could split and `(LINKED)` force a join: a later task, only with Katlego's say |

## Anatomical fidelity

What it says, for the limb agent (limb-agent.md):

- **Four kinds of anatomy fault** (from Distortion-5K, arXiv [2503.00811](https://arxiv.org/abs/2503.00811)):
  - *proliferation*: an extra limb or finger;
  - *absence*: a limb or digit missing;
  - *deformation*: a joint bent the wrong way, an impossible twist;
  - *fusion*: two structures grown into one, **including a limb merged into clothing or an
    object**.

  The 14 Oct prototype's `Defect` list covers the first three and fused *bodies*, but not a limb
  fused into an object. It goes to limb-agent.md §10 for a second prompt. The first run stays on
  the prototype's prompt (§8).
- **How common it is:** the report says about half of human figures from current models have a
  measurable fault, citing Distortion-5K. That is not our rate: Tumo's 109 labelled frames have no
  anatomy label (#194: they were about the script); Katlego's T111 labels found 16 defects in them
  (findings § U9).
- **Small hands are where it goes wrong.** At 512 px a hand gets about 6 × 6 latent tokens. Faults
  should cluster in wide shots, where the vision model also sees least. So T111 reports recall by
  framing.
- **Answers that point at the fault:** the report's diagnostic model (ARGUS, in Diagnose-to-Generate,
  arXiv 2610.17882) names the fault *and its box*, and is scored on whether the box lands. A box
  per defect makes the agent's answers checkable by eye. It goes to limb-agent.md §10 for a second
  prompt.
- **Fixing instead of redrawing:** the report describes two ways to repair a fault without a full
  redraw:
  - detect the hand, crop it with about 30 px of margin, upscale and inpaint it at denoise
    0.35–0.55 (the ADetailer method);
  - fit a 3D hand mesh and inpaint from its depth map (HandRefiner, arXiv
    [2311.17957](https://arxiv.org/abs/2311.17957)).

  Our loop redraws the whole frame. A regional fix would need an inpainting endpoint and a hand
  box. It's out of T111's scope and recorded as a later option.
- **Not for us:**
  - Negative prompts and negative embeddings: the report finds them unreliable for counts, and our
    fal klein request sends none (storyboard.md §3.5).
  - Pose or depth ControlNets (DWPose, DensePose, SMPL-X): these need the ComfyUI GPU path, which
    was cut (T003, 2026-10-19).
