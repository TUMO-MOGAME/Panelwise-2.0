# Panelwise 2.0: bootcamp plan

> Panelwise rebuilt on Tether's local stack for the Tether × GAIC Advanced AI Foundations Bootcamp.
> Provenance: [CHANGES-FROM-PANELWISE.md](CHANGES-FROM-PANELWISE.md). The bootcamp's own plan and resources live one folder up,
> in `../plan.md`, `../resources.md` and `../sdks.md`. **Rule: only Tether's ecosystem** (QVAC, Fabric, WDK, Holepunch/Pears).

## Why Panelwise fits the bootcamp

Panelwise's promise is that **every panel traces to a verbatim span of the script**, and code, not the model, checks every
quote. That is the same discipline Tether's own QVAC examples teach: do the arithmetic and checks in code, force structured
output, never trust the model. Running it locally adds the bootcamp's three reasons for local AI:

- **Privacy:** an unreleased screenplay never leaves the writer's machine. That's a real concern for writers and studios.
- **Cost:** no per-token or per-image bill, so the monthly caps (2.8M tokens, 800 drawings) disappear.
- **Offline:** it works on a laptop with no connection once the models are cached.

## Where the cloud sits today (the only two places to change)

| Seam | File | Today | QVAC replacement |
|---|---|---|---|
| Chat, 3 tiers (fast / reasoning / vision) | `services/api/app/llm/client.py` (`NebiusChatModel`, OpenAI-compatible) | Nemotron on Token Factory | **`qvac serve --openai`** at `http://localhost:11434/v1`. Mostly config: `NEBIUS_BASE_URL` + model aliases |
| Drawing | `services/api/app/storyboard/fal.py` (`FalRenderer`, via `fal_factory`) | FLUX.2 [klein] 4B on fal.ai | A `QvacRenderer` posting to `/v1/images/generations` with the **same model**, `FLUX_2_KLEIN_4B_Q4_0` |
| Storage, Postgres, Auth | Supabase | hosted | Local Postgres from `docker-compose.yml` for now. Holepunch (Hyperdrive/Hyperbee) is a later question |

## Steps

1. **Run it as it is**, locally with `docker compose`, on cloud keys, to get a baseline. *Optional if the keys are gone.*
2. **`qvac.config.json`** with aliases: `fast` = `QWEN3_1_7B_INST_Q4`, `reasoning` = `QWEN3_4B_INST_Q4_K_M`,
   `vision` = `QWEN3_5_4B_MULTIMODAL_Q4_K_M`, `draw` = `FLUX_2_KLEIN_4B_Q4_0`. Run `qvac configure` to check the exact entries.
3. **Point the LLM client at QVAC.** Make the provider name neutral, check JSON output and `<think>` handling against Qwen3,
   and re-run the grounding and shot-planning evals (`eval/`) to **measure** faithfulness and recall against the Nemotron numbers.
4. **`QvacRenderer`**, then time a frame on this laptop (Intel iGPU, Vulkan). If it's too slow, drop the size or steps,
   or split the work across machines with QVAC RPC.
5. **Frame audit on a local VL model**, re-scored on the 109 hand-labelled frames.
6. **Narration** (T113) with QVAC TTS. Optional: South African languages via AfriSLM translation.
7. **Week 2 (WDK):** to decide. One idea is to **pay a storyboard artist or co-writer in USD₮** for a finished board, with a
   human approving.
8. **Ship:** README for strangers, demo video, offline demo, upstream issues found on Windows/iGPU.

## Risks

- **Memory:** this laptop has 31.5 GB RAM shared with an iGPU, and the browsers often use ~29 GB of it. Load one model at a time.
- **Speed:** FLUX locally on an iGPU may take minutes a frame. Measure it, don't assume it.
- **Quality:** a 4B model in place of a 120B reasoning model will lose accuracy. Panelwise's evals let us **say how much**,
  and that honesty is a strength in front of judges.
- **Python:** the API needs Python 3.14 and `uv`, which the bootcamp setup didn't cover. Check this before step 1.
