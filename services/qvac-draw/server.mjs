// Panelwise 2.0's drawing server: FLUX.2 [klein] through Tether's QVAC SDK, with the sampling
// settings klein needs. `qvac serve --openai` drops every field of POST /v1/images/generations but
// prompt, size, seed and n (@qvac/cli 0.18.0, extractImageGenerationParams), so `steps` and
// `cfg_scale` never reach the engine. This answers the same request, passing them through, as
// Tether's own example does (@qvac/sdk dist/examples/diffusion-flux2-klein.js). Text stays on
// `qvac serve`. Run from the repo root (QVAC reads ./qvac.config.json):
//
//   node services/qvac-draw/server.mjs            # port 11436, the `draw` alias of qvac.config.json
//
// Endpoints: POST /v1/images/generations, DELETE /v1/models/:alias (unload), GET /health.
// Loopback only. One drawing at a time; the model loads on the first request and unloads after
// QVAC_DRAW_IDLE_S (default 600) idle seconds, so a text model can have the memory back.

import fs from "node:fs";
import http from "node:http";
import path from "node:path";

import * as sdk from "@qvac/sdk";

const PORT = Number(process.env.QVAC_DRAW_PORT ?? 11436);
const IDLE_S = Number(process.env.QVAC_DRAW_IDLE_S ?? 600);
const CONFIG = path.resolve(process.env.QVAC_CONFIG ?? "qvac.config.json");
const ALIAS = process.env.QVAC_DRAW_ALIAS ?? "draw";
const MAX_BODY = 64 * 1024;

const entry = JSON.parse(fs.readFileSync(CONFIG, "utf8")).serve.models[ALIAS];
if (!entry) throw new Error(`no "${ALIAS}" model in ${CONFIG}`);

/** A catalog constant's name (FLUX_2_KLEIN_4B_Q4_0) as the SDK's object; anything else as given. */
const source = (name) => (typeof name === "string" && name in sdk ? sdk[name] : name);

const modelConfig = Object.fromEntries(
  Object.entries(entry.config ?? {}).map(([k, v]) => [k, k.endsWith("ModelSrc") ? source(v) : v]),
);

let modelId = null;
let loading = null;
let idleTimer = null;
let queue = Promise.resolve(); // one drawing at a time

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function ensureLoaded() {
  if (modelId) return modelId;
  loading ??= (async () => {
    const t = Date.now();
    log(`loading ${entry.model} (${JSON.stringify(entry.config ?? {})})`);
    const id = await sdk.loadModel({ modelSrc: source(entry.model), modelType: "sdcpp-generation", modelConfig });
    log(`loaded in ${((Date.now() - t) / 1000).toFixed(1)} s`);
    modelId = id;
    return id;
  })().finally(() => (loading = null));
  return loading;
}

async function unload() {
  clearTimeout(idleTimer);
  if (!modelId) return false;
  const id = modelId;
  modelId = null;
  await sdk.unloadModel({ modelId: id, clearStorage: false });
  log("unloaded");
  return true;
}

function armIdle() {
  clearTimeout(idleTimer);
  if (IDLE_S > 0) idleTimer = setTimeout(() => void (queue = queue.then(unload, unload)), IDLE_S * 1000);
}

const int = (v, lo, hi) => (Number.isInteger(v) && v >= lo && v <= hi ? v : undefined);
const num = (v, lo, hi) => (typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi ? v : undefined);

/** The request as the SDK takes it; klein's defaults (4 steps, no CFG) when a field is absent. */
function params(body) {
  if (typeof body.prompt !== "string" || !body.prompt) throw new Error('"prompt" is required');
  const m = /^(\d+)x(\d+)$/.exec(body.size ?? "512x512");
  if (!m) throw new Error('"size" must be WIDTHxHEIGHT');
  const [width, height] = [Number(m[1]), Number(m[2])];
  if (width % 8 || height % 8 || width > 2048 || height > 2048) throw new Error('"size" must be multiples of 8, at most 2048');
  const p = {
    prompt: body.prompt,
    width,
    height,
    steps: int(body.steps, 1, 100) ?? 4,
    cfg_scale: num(body.cfg_scale, 0, 30) ?? 1,
    seed: int(body.seed, -1, 2 ** 32 - 1) ?? -1,
  };
  const guidance = num(body.guidance, 0, 30);
  if (guidance !== undefined) p.guidance = guidance;
  if (typeof body.sampling_method === "string") p.sampling_method = body.sampling_method;
  if (typeof body.scheduler === "string") p.scheduler = body.scheduler;
  return p;
}

async function draw(p) {
  clearTimeout(idleTimer);
  const id = await ensureLoaded();
  const t = Date.now();
  const { progressStream, outputs } = sdk.diffusion({ modelId: id, ...p });
  let last = 0;
  for await (const { step, totalSteps } of progressStream) {
    log(`step ${step}/${totalSteps} at ${((Date.now() - t) / 1000).toFixed(1)} s`);
    last = totalSteps;
  }
  const [png] = await outputs;
  log(`drew ${p.width}x${p.height}, ${last} steps, cfg ${p.cfg_scale}, in ${((Date.now() - t) / 1000).toFixed(1)} s`);
  armIdle();
  return png;
}

function send(res, status, body) {
  const text = JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(text) });
  res.end(text);
}

const fail = (res, status, message) => send(res, status, { error: { message } });

async function readJson(req) {
  let size = 0;
  const chunks = [];
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) throw new Error("body too large");
    chunks.push(c);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (req.method === "GET" && url.pathname === "/health") {
      return send(res, 200, { ok: true, alias: ALIAS, loaded: modelId !== null });
    }
    if (req.method === "DELETE" && url.pathname === `/v1/models/${ALIAS}`) {
      const freed = await (queue = queue.then(unload, unload));
      return send(res, 200, { id: ALIAS, object: "model", deleted: freed });
    }
    if (req.method === "POST" && url.pathname === "/v1/images/generations") {
      let p;
      try {
        const body = await readJson(req);
        if (body.model !== undefined && body.model !== ALIAS) return fail(res, 404, `unknown model "${body.model}"`);
        p = params(body);
      } catch (err) {
        return fail(res, 400, err.message);
      }
      const job = queue.then(() => draw(p));
      queue = job.catch(() => {});
      const png = await job;
      return send(res, 200, { created: Math.floor(Date.now() / 1000), data: [{ b64_json: Buffer.from(png).toString("base64") }] });
    }
    return fail(res, 404, "not found");
  } catch (err) {
    log("error:", err?.message ?? err);
    return fail(res, 500, "drawing failed");
  }
});

server.listen(PORT, "127.0.0.1", () => log(`QVAC drawing server on http://127.0.0.1:${PORT}, alias "${ALIAS}"`));

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, async () => {
    await unload().catch(() => {});
    process.exit(0);
  });
}
