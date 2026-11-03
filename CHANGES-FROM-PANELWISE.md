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
| Text models (fast / reasoning tiers) | Nemotron on Nebius Token Factory | **Working (2026-11-03):** Qwen3 1.7B / 4B via `qvac serve --openai` on the device (`qvac.config.json`, `LLM_THINKING_FIELD`); evals not yet re-run |
| Vision model (frame audit) | Nemotron 3.5 Super VL | *planned:* a QVAC multimodal model (Qwen3.5 / Qwen3-VL) |
| Drawing | FLUX.2 [klein] 4B on fal.ai | *planned:* FLUX.2 [klein] 4B **locally** through QVAC diffusion |
| Narration (was a stretch, T113, ElevenLabs) | not built | *planned:* QVAC text-to-speech |
| Hosting | Vercel + Render + Supabase | *to decide:* local-first |
