# Changes from Panelwise

Panelwise 2.0 starts from **Panelwise**, the team's entry to the Nebius × NVIDIA Global AI Hackathon:
<https://github.com/Katlego-tech/Panelwise> (Apache-2.0), copied at commit `08e9705` on 2026-11-03.

- **Original authors:** Tumo Mogame and Katlego Tlhapiso. The full commit history (1,021 commits) stays in the original repo.
  This repo starts from a clean import, so `git blame` here does not show who wrote the imported code. The original repo does.
- **Licence:** Apache-2.0, unchanged. See [LICENSE](LICENSE).
- **Why a new repo:** Panelwise 2.0 is the entry to the **Tether × GAIC Advanced AI Foundations Bootcamp** (Cohort 1,
  2–14 Nov 2026), whose rule is that AI runs **on the device**. It moves Panelwise off cloud AI (Nemotron on Nebius Token Factory,
  FLUX.2 [klein] on fal.ai) and onto **Tether's QVAC** local stack. The bootcamp allows existing projects.

## What changes

The bootcamp plan, with what's done and what isn't yet, is in [BOOTCAMP.md](BOOTCAMP.md). Each change will be listed here as it lands.

| Area | Panelwise | Panelwise 2.0 |
|---|---|---|
| Text models (fast / reasoning tiers) | Nemotron on Nebius Token Factory | **Working:** Qwen3 4B Instruct for both tiers via `qvac serve --openai` on the device (`qvac.config.json`, `LLM_THINKING_FIELD`); first local eval 2026-11-03 (with 1.7B as the fast tier), not yet re-run on 4B alone |
| Vision model (frame audit) | Nemotron 3.5 Super VL | *planned:* a QVAC multimodal model through the SDK. Until then every frame is shown as **"Not checked"**, on the board and in the PDF |
| Drawing | FLUX.2 [klein] 4B on fal.ai | **Working (2026-11-07):** FLUX.2 [klein] 4B on the device through the QVAC SDK ([services/qvac-draw](services/qvac-draw/README.md)): 38 s a frame at 512 × 288 on an Intel iGPU; 23 frames of a script drawn live with no errors |
| Narration (was a stretch, T113, ElevenLabs) | not built | *planned:* QVAC text-to-speech |
| Hosting | Vercel + Render + Supabase | **Local mode (2026-11-03):** one user, files on disk, local Postgres, no Supabase (`PANELWISE_LOCAL_TOKEN`, `scripts/dev-local.ps1`). The Supabase path still works when the token is unset |
| Storyboard PDF | Footer names Nemotron | **2026-11-07:** the footer names no model, and a frame no vision model looked at says "Not checked" |
