# Migrating the audit's vision model to Nemotron 3.5 Super VL

**For:** Tumo · **From:** Katlego (via Claude), 2026-10-17 · **Decision:** made (Katlego): Super VL
replaces DeepSeek-V4.1-Flash for every vision call · **Design:**
[docs/design/vision-model.md](design/vision-model.md) (T105) · **Measurement:**
[nebius-findings.md § U8](nebius-findings.md#u8--an-nvidia-vision-model-2026-10-17)

---

## The pitch

**Every model call in Panelwise becomes NVIDIA's.** Until 12 Oct, Token Factory had no NVIDIA model
that takes an image, so the audit has had to say "a vision model describes each frame; Nemotron
judges it", with a non-NVIDIA model doing the seeing (option A, findings § The vision decision).
NVIDIA released Nemotron 3.5 Super VL on 15 Oct and it is on Token Factory. With it:

- **The pitch line becomes true end to end:** Nemotron reads the script, plans the shots, **sees
  every frame** and judges it. For a Nebius × NVIDIA hackathon, the judged section *Sponsor
  Technologies Deployed* reads as one stack instead of "Nemotron, plus another vendor's model for
  the part that matters most".
- **It already fits.** With thinking off, measured on the-red-kite's 44 stored drawings
  (findings § U8): 0 errors, 0.95× the tokens, 1.43× the median time. It was right on 7 of the 10
  disputed hard checks, the same as DeepSeek, and it withholds the one truly wrong frame DeepSeek
  shows.
- **Most of the audit carries over unchanged:** the strict JSON schemas (0 repairs); the people
  described (44 of 44 the same); the sex agent (48 of 48 answers the same); the judge's matches (36
  of 44 the same, and of the real differences Super VL is right on 3 and DeepSeek on 1).
- **It's cheaper per output token** ($0.90 against $1.20 per million) and needs no money and no new
  service: one setting, the same Token Factory key, and the hosted caps unchanged.
- **The risk is small and reversible in minutes** (§ Rollback).

**What didn't carry over**, which is what the plan below fixes. These were tuned on
DeepSeek's wording, and none of them shows a wrong frame on the hosted demo:
1. **Rooftops read as "interior"** (2 of 44): a `setting` hard fail on a right frame. **Fixed
   18 Oct (T106, #209/#210):** both rooftops pass, no other setting changed.
2. **More lettering, less "signature"**: text entries 9 → 25, `text_in_frame` warnings 6 → 22. The
   artists' scrawled signatures read as text, which makes more warnings on the cards and never a
   withheld frame. **Fixed 18 Oct (T107, #209/#210):** a `signature_text` field written before
   `text` brings `text_in_frame` to 5 frames (findings § U8 follow-ups).
3. **Hair wording (still open, T108, Tumo):** "pigtails" where the script says "braids tied back", so the judge refuses the
   match (`unscripted_person`). Once with thinking off (storyboard 4.1), six times with it on;
   that's why thinking stays off.

## The plan

| When | Step | Who | Task |
|---|---|---|---|
| **17 Oct** ✅ done | Switch the defaults: `NEBIUS_MODEL_VISION=nvidia/Nemotron-3.5-Super-VL`, `NEBIUS_VISION_THINKING=false`. Merge #191, then #192 (retargeted to `main`). Render redeploys the API and the hosted demo audits with Super VL | Katlego (Claude) | T105 |
| **18–19 Oct** ✅ done (17 Oct, § U8 held out; #194, #200) | **Translation on a held-out script:** your stored the-lighthouse-inspector (or the-borrowed-bicycle), DeepSeek against Super VL with thinking off, with the script in #192's comment; your table goes into § U8 beside the-red-kite's. It tells us whether the three items above are all there is | **Tumo** | T105 |
| 18–20 Oct ✅ done 18 Oct (#209, #210) | A rooftop or a roof-level space open to the sky is `exterior`: the describer's setting rule, measured with `reaudit` on the stored drawings | Katlego (Claude) | T106 |
| 18–20 Oct ✅ done 18 Oct (#209, #210: a `signature_text` field; `text_in_frame` 22 → 5) | Signatures against lettering, re-tuned for Super VL's wording (T077's rule), measured the same way | Katlego (Claude) | T107 |
| **20–22 Oct** (T108 open; T102, T104 and T097 merged 18 Oct) | The look match: the judge accepts a described hairstyle that is the script's under another word (pigtails, plaits, braids); this sits in your T080 look rule. Also re-measure the open agents on Super VL as they land: T102's questions, T104's layout, T097's heads | **Tumo** | T108; T102, T104 Verify |
| **20 Oct** ✅ done (planned 23 Oct) | The judge sample drawn on the hosted stack, audited by Super VL, and copied to the judge account (`seed --from`) | both | T030 |
| 24–26 Oct (SPEC and about.md done; README pending, T033; the video not recorded, T034) | The wording: README, SPEC and `docs/submission/about.md` say "Nemotron 3.5 Super VL describes each frame; Nemotron Super judges it", and the video says it too | both | T033, T034 |

**What it costs:** about $0.15 of Token Factory credit a measuring run (40-odd stored attempts),
and nothing on fal (no drawings). The monthly token cap stays 2,800,000, since Super VL uses 0.95×
DeepSeek's tokens.

**Limits:** Super VL allows 300 requests and 2M tokens a minute on Token Factory (DeepSeek: 3,000
and 1M). A storyboard makes roughly 50–150 vision calls (a description and the agents' questions
for each of 22-odd frames, up to 3 attempts each) over several minutes, so 300 a minute is ample. The hosted judge sample ran on it on 20 Oct.

## Rollback

If the hosted audit misbehaves, set **`NEBIUS_MODEL_VISION=deepseek-ai/DeepSeek-V4.1-Flash`** and
**`NEBIUS_VISION_THINKING=`** (blank) in Render's dashboard (*panelwise-api → Environment*). A
dashboard variable overrides the code default, and Render restarts the API with it in about a
minute, with no code change and no migration. Record it in STATUS.md, and remove the variables once
it is fixed in code, so `render.yaml` and the code stay the source of truth.

## What to tell a judge

*"Every model call is Nemotron on Nebius Token Factory: Nemotron 3.5 Lightning extracts the
characters and plans the shots, Nemotron 3.5 Super VL looks at every drawn frame, and Nemotron Super
judges it against the script before anything is shown."* True since the 17 Oct step was merged and
deployed. (A body drawn wrong is not checked: T111 measured Super VL on it and didn't adopt it,
findings § U9.)
