# `storyboard`

One frame per shot, the style registry (public styles plus an optional private pack), and the storyboard PDF.
Design: [docs/design/storyboard.md](../../../../docs/design/storyboard.md).

- `styles.py` (T008): `load_styles` reads `styles/*.toml` and the private pack, and rejects a bad file at start-up.
- `prompt.py` (T008): `build_frame_prompt`, a pure function; every script part is tagged with the span it came from.
- `prompts.py` (T008): `uv run python -m app.storyboard.prompts <script.pdf> [--style KEY]` prints every shot's prompt, part by part, on the real account.
- `fal.py` (T026): `FalRenderer`, the renderer on fal.ai: FLUX.2 [klein] 4B (`FAL_MODEL`, since 2026-10-11; FLUX.1 [schnell] before) (storyboard.md §3.5). `workflow.py`: `fit`, the grayscale pass, the render key. `render.py`: `RendererError`, `RenderRecord`, the rendering stage's failure copy.
- `build.py` (T026): `build_storyboard`, every shot through verify's loop and T021's writer; `run_job` runs it as the upload's RENDERING stage when the app has a renderer (`FAL_KEY` set).
- `document.py` (T027): the storyboard PDF. ComfyUI on a Nebius GPU (T003) was cut 2026-10-19 and never built; fal.ai is the only renderer.
