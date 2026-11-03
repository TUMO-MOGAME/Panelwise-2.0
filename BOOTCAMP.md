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
2. ✅ **`qvac.config.json`** (2026-11-03): `fast` = `QWEN3_1_7B_INST_Q4`, `reasoning` = `QWEN3_4B_INST_Q4_K_M`, both loaded
   on first use, one load at a time. Run `qvac serve --openai --port 11435` from the repo root. Port 11435 because Ollama
   holds QVAC's default 11434 on this laptop. Free a model's memory with `curl -X DELETE http://127.0.0.1:11435/v1/models/fast`.
   `vision` and `draw` aren't in it yet (see steps 4 and 5).
3. 🔄 **Point the LLM client at QVAC.** Done (2026-11-03): `LLM_THINKING_FIELD=reasoning_budget` (QVAC ignores vLLM's
   `chat_template_kwargs`), no key needed for a loopback URL, and the QVAC block in `.env.example`.
   `tools/qvac_smoke.py` runs a JSON call through the app's own client. **First local results** (warm call, 32 GB Intel
   Core Ultra 7 265U, Vulkan iGPU; tok/s includes prompt processing):

   | Tier | Model | Cold (load + call) | Warm | Tok/s (warm) | Answer |
   |---|---|---|---|---|---|
   | fast | Qwen3 1.7B Q4_0 | 40.2 s | 2.2 s | 17.3 | valid JSON, kept "(60s, oilskin coat)" in the name |
   | reasoning | Qwen3 4B Q4_K_M | 17.6 s | 3.3 s | 8.0 | valid JSON, clean ("Mara") |

   Still to do: re-run the grounding and shot-planning evals (`eval/`) to **measure** faithfulness and recall against the
   Nemotron numbers. Make the provider name neutral (`NEBIUS_*` → `LLM_*`) once the evals are in.
   Note: `QWEN3_4B_INST` is an instruct-only build and does no thinking, so `reasoning` thinks less than Nemotron did.
   If the evals show it matters, try a thinking-capable Qwen3 build.
4. **`QvacRenderer`**, then time a frame on this laptop (Intel iGPU, Vulkan). If it's too slow, drop the size or steps,
   or split the work across machines with QVAC RPC.
4b. FLUX.2 [klein] needs two companions besides `FLUX_2_KLEIN_4B_Q4_0`: a Qwen3 4B text encoder (`QWEN3_4B_Q4_K_M`) and
   `FLUX_2_KLEIN_4B_VAE`. See the diffusion example in `../reference/qvac-llms-full.txt`.
5. **Frame audit on a local VL model**, re-scored on the 109 hand-labelled frames. **`qvac serve`'s chat endpoint silently
   drops image parts**, so the vision tier can't go through it. It needs the SDK directly (a small Node sidecar) instead.
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
