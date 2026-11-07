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
| Chat, 3 tiers (fast / reasoning / vision) | `services/api/app/llm/client.py` (`NebiusChatModel`, OpenAI-compatible) | Nemotron on Token Factory | ✅ **`qvac serve --openai`** at `http://127.0.0.1:11435/v1`, both text tiers on Qwen3 4B. Vision: not yet (step 5) |
| Drawing | `services/api/app/storyboard/fal.py` (`FalRenderer`, via `fal_factory`) | FLUX.2 [klein] 4B on fal.ai | ✅ `QvacRenderer` (`app/storyboard/qvac.py`) with the **same model**, `FLUX_2_KLEIN_4B_Q4_0`, through [services/qvac-draw](services/qvac-draw/README.md) on the QVAC SDK |
| Storage, Postgres, Auth | Supabase | hosted | ✅ **Local mode** (2026-11-03): `PANELWISE_LOCAL_TOKEN` swaps Supabase Auth for one local user (`LocalVerifier`) and Storage for files on disk (`LocalStore`, HMAC-signed links served by `/api/v1/files`); Postgres from `docker-compose.yml`. Holepunch (Hyperdrive/Hyperbee) is a later question |

## Run it on this laptop

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-local.ps1
```

It starts Postgres (Docker, port 5433), `qvac serve` (port 11435) and the drawing server (port 11436) if they aren't
running, the API (:8000) and the web app (:3000), each in its own window, with a fresh local token and no Supabase or
fal.ai. Open <http://localhost:3000>: there's no sign-in. An upload reads, extracts and plans on Qwen3 4B, then draws
every frame with FLUX.2 [klein] at 512 × 288, fitted to 1280 × 720. `-TextOnly` skips the drawing.

## Steps

1. **Run it as it is**, locally with `docker compose`, on cloud keys, to get a baseline. *Optional if the keys are gone.*
2. ✅ **`qvac.config.json`** (2026-11-03): first `fast` = `QWEN3_1_7B_INST_Q4` and `reasoning` = `QWEN3_4B_INST_Q4_K_M`;
   now both tiers use `qwen3-4b` (one loaded model serves both), and `draw` is FLUX.2 [klein]. Each loads
   on first use, one load at a time. Run `qvac serve --openai --port 11435` from the repo root. Port 11435 because Ollama
   holds QVAC's default 11434 on this laptop. Free a model's memory with `curl -X DELETE http://127.0.0.1:11435/v1/models/fast`.
   `vision` isn't in it yet (step 5).
3. 🔄 **Point the LLM client at QVAC.** Done (2026-11-03): `LLM_THINKING_FIELD=reasoning_budget` (QVAC ignores vLLM's
   `chat_template_kwargs`), no key needed for a loopback URL, and the QVAC block in `.env.example`.
   `tools/qvac_smoke.py` runs a JSON call through the app's own client. **First local results** (warm call, 32 GB Intel
   Core Ultra 7 265U, Vulkan iGPU; tok/s includes prompt processing):

   | Tier | Model | Cold (load + call) | Warm | Tok/s (warm) | Answer |
   |---|---|---|---|---|---|
   | fast | Qwen3 1.7B Q4_0 | 40.2 s | 2.2 s | 17.3 | valid JSON, kept "(60s, oilskin coat)" in the name |
   | reasoning | Qwen3 4B Q4_K_M | 17.6 s | 3.3 s | 8.0 | valid JSON, clean ("Mara") |

   **First eval on local models** (2026-11-03, 1 run a sample, [eval/README.md](eval/README.md)): faithfulness 0.81
   (Nemotron 0.90), recall 0.72 (0.94), **0 ungrounded kept** (the code check still catches every made-up quote), about 2×
   the shots, 3.5–10 min a sample. Weakest on `sipho-and-siphokazi` (0.40 / 0.25). Next: find out why (names? the 1.7B
   fast tier?), try `reasoning` on extraction, then 5 runs. Make the provider name neutral (`NEBIUS_*` → `LLM_*`) after.
   Note: `QWEN3_4B_INST` is an instruct-only build and does no thinking, so `reasoning` thinks less than Nemotron did.
   If the evals show it matters, try a thinking-capable Qwen3 build.
4. ✅ **`QvacRenderer`**, timed on this laptop (Intel iGPU, Vulkan), 2026-11-07:

   | One frame | 512 × 288 | 848 × 480 |
   |---|---|---|
   | through `qvac serve` | 408 s | 924 s |
   | through the SDK ([services/qvac-draw](services/qvac-draw/README.md)), 4 steps, CFG 1 | **38 s** | **120 s** |

   `qvac serve` (`@qvac/cli` 0.18.0) drops `steps` and `cfg_scale` from the request (`extractImageGenerationParams`
   copies only prompt, size, seed and n), so klein didn't run at its 4 steps. The drawing server calls the SDK's
   `diffusion()` directly, as Tether's `diffusion-flux2-klein.js` example does. **A whole script, live** (2026-11-07):
   23 frames, about 15 min reading and planning, then about 17 min drawing (about 47 s a frame), no errors.
   Built 2026-11-03: `app/storyboard/qvac.py` (`QvacRenderer`, alias `draw`), tested. Until a QVAC
   vision path exists (step 5), a frame is shown as a warning with no checks. Model download: QVAC's P2P registry stalled
   on this network, so the catalog files were fetched from their pinned source and checked against the catalog's
   SHA-256 before entering `~/.qvac/models`. The text encoder is the cached `QWEN3_4B_INST_Q4_K_M`.
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
- **Speed:** measured: 38 s a frame at 512 × 288 on the iGPU (step 4). Reading and planning a script (about 15 min) is
  now as slow as drawing it.
- **Quality:** a 4B model in place of a 120B reasoning model will lose accuracy. Panelwise's evals let us **say how much**,
  and that honesty is a strength in front of judges.
- **Python:** the API needs Python 3.14 and `uv`, which the bootcamp setup didn't cover. Check this before step 1.
