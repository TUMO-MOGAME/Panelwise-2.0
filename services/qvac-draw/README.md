# qvac-draw: FLUX.2 [klein] through the QVAC SDK

Panelwise 2.0's drawing server. It answers the OpenAI-style `POST /v1/images/generations` that the API sends, and draws
through `@qvac/sdk`'s `diffusion()`, so FLUX.2 [klein] runs at the 4 steps without CFG it was distilled for.

## Why it exists

`qvac serve --openai` (`@qvac/cli` 0.18.0) builds the drawing parameters in `extractImageGenerationParams`
(`dist/serve/extensions/openai/schemas/images.js`). It copies only `prompt`, `size`, `seed` and `n` from the request
body, so `steps` and `cfg_scale` never reach the engine. Measured on an Intel Core Ultra 7 265U (32 GB RAM, integrated
GPU over Vulkan), 7 Nov 2026:

| One frame | 512 × 288 | 848 × 480 |
| --- | --- | --- |
| `qvac serve`, `"steps": 4` sent but dropped | 408 s | 924 s |
| this server, `steps: 4`, `cfg_scale: 1` | 38 s | 120 s |

Turning flash attention off (`diffusion_fa: false`) made it slower (47 s at 512 × 288), so it stays on.

## What it does

- Reads the `draw` alias from `./qvac.config.json` (run it from the repo root), and maps the catalog names there
  (`FLUX_2_KLEIN_4B_Q4_0`, `QWEN3_4B_INST_Q4_K_M`, `FLUX_2_KLEIN_4B_VAE`) to the SDK's model constants.
- Loads the model with `loadModel({ modelType: "sdcpp-generation", ... })` on the first request, then unloads it after
  `QVAC_DRAW_IDLE_S` seconds idle (600 by default), so the text model can have the memory back.
- Draws one image at a time. `steps` defaults to 4 and `cfg_scale` to 1. `guidance`, `sampling_method` and `scheduler`
  are passed on when sent.
- Listens on 127.0.0.1 only.

| Endpoint | What |
| --- | --- |
| `POST /v1/images/generations` | `{prompt, size: "WxH", seed, steps, cfg_scale}` (one image a request) → `{created, data: [{b64_json}]}` |
| `DELETE /v1/models/draw` | unload FLUX now |
| `GET /health` | up, and whether the model is loaded |

## Run it

`scripts/dev-local.ps1` starts it for you. On its own, with Node 22.21.1:

```powershell
cd services\qvac-draw; npm install; cd ..\..
node services\qvac-draw\server.mjs        # port 11436; QVAC_DRAW_PORT to change it
```

The API uses it when `QVAC_DRAW_URL=http://127.0.0.1:11436/v1` is set. Without that, it draws through `qvac serve`.
