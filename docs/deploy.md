# Deploying Panelwise

The one-time setup of the three hosted services, in the order they depend on each other. Design and
reasons: [docs/design/deploy.md](design/deploy.md). Every secret goes into a dashboard, never into
the repo. Each step ends with a check; don't start the next until it passes.

| Order | Service | Runs | Needs |
|---|---|---|---|
| 1 | Supabase | Postgres, Storage and Auth | an account |
| 2 | Render | the API (`services/api`, from `render.yaml`) | the GitHub repo, step 1's connection string and keys, the Nebius key |
| 3 | Vercel | the web app (`apps/web`) | the GitHub repo, step 2's domain |

**Since 2026-10-08 (Katlego; a paid plan since 2026-10-11):** the API runs on **Render**, not Railway (T063, #80/#81).
The web can go first, before any API: see **Web first** in step 3.

## 1. Supabase — the database

1. supabase.com → New project. Pick an EU region near Render's `frankfurt` (`render.yaml`); ours is
   eu-west-1, Ireland. Save the database password in a password manager.
2. **Connect** → **Session pooler** (port **5432**). Copy that connection string, with the password
   filled in. Not the *direct* connection: it's IPv6-only without the paid add-on. Not the
   *transaction* pooler (6543): it can't do prepared statements, which the API's driver uses.
3. Project Settings → API Keys: note the project URL and the **secret** key (for step 2, server
   only) and the **publishable** key (for step 3; the browser sign-in, T040, uses it).

**Check:** from your machine, with the session-pooler string in `DATABASE_URL`:

```bash
cd services/api && DATABASE_URL='postgresql://…pooler.supabase.com:5432/postgres' \
  uv run uvicorn app.main:app --port 8001 &
sleep 3 && curl -s localhost:8001/api/v1/health   # {"status":"ok","checks":{"postgres":"ok"}}
kill %1
```

## 2. Render — the API

The service is defined in `render.yaml` at the repository root (a Render Blueprint: a Docker web
service on plan **`1c-2g`** (1 CPU, 2 GB, about $25 a month; Render called it Standard before
26 Aug 2026; chosen over `0.5c-512mb` by the memory check, design §9), Frankfurt; design: [deploy.md §6](design/deploy.md)). Change settings there, in a
PR, not in the dashboard: a dashboard edit to a field the Blueprint sets may be overwritten the next time it syncs.

1. render.com → sign in with GitHub → give Render access to `Katlego-tech/Panelwise`.
2. **New → Blueprint** → pick the repo, branch `main`, Blueprint path `render.yaml`. Render lists
   one service, `panelwise-api`, and asks for the seven values marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | step 1's session-pooler string, as copied: **not** the local `.env`'s `DATABASE_URL`, which is the compose Postgres on `localhost` (the first deploy failed on exactly that, 2026-10-16: `Connect call failed ('127.0.0.1', 5432)` and the container exits). `postgresql://…` is fine (the API adds `+asyncpg`), and so is `?sslmode=require` (the API turns it into asyncpg's `?ssl=require`) |
   | `NEBIUS_API_KEY` | your Token Factory key |
   | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | step 1 (the token check and uploads from T053, frames from T026) |
   | `FAL_KEY` | your fal.ai key (the renderer, T026). Without it the API starts with no renderer: uploads stop at planning |
   | `LLM_MONTHLY_TOKEN_CAP`, `IMAGE_MONTHLY_GENERATION_CAP` | the figures recorded in [design §6](design/deploy.md) (limits.md §10). **Never blank:** blank is off, an uncapped bill |

   `AUDIT_WITHHOLD_CHECKS`, `UPLOADS_PER_DAY` and `UPLOAD_MAX_PAGES` come with their values from
   `render.yaml` (T030).

   Everything else has a default in `app/core/config.py` (`NEBIUS_MODEL_*`, `LLM_*`,
   `SUPABASE_STORAGE_BUCKET=panelwise`, `FAL_MODEL`, `RENDER_MAX_ATTEMPTS=3`). `PORT` is set by Render (10000), and the container listens
   on it. Never set `PANELWISE_PRIVATE_STYLES` here.
3. **Apply.** Render builds `services/api/Dockerfile` and starts
   it; the image's start command runs `alembic upgrade head`, then uvicorn. Render switches traffic
   once `/api/v1/health` answers 200. A failed migration exits the container, so the deploy never
   turns healthy and Render cancels it. The service's URL is `https://panelwise-api.onrender.com` (or with
   a suffix if the name is taken; it's on the service's page).
4. **The uptime alert.** On GitHub: the repo's Settings → Secrets and variables → Actions →
   **Variables** → New repository variable `API_HEALTH_URL` = `https://<render-domain>/api/v1/health`.
   The `keep-alive` workflow (`.github/workflows/keepalive.yml`) then calls it every 10 minutes: a
   failed run emails you that the demo is down, and its Postgres check keeps a free Supabase project
   from pausing for inactivity. (The paid instance itself never sleeps.)

From then on, a push to `main` that touches `services/api/**` deploys after its GitHub checks pass
(`autoDeployTrigger: checksPass`). A deploy that fails its migration or isn't healthy within
15 minutes is cancelled, and the previous one keeps serving.

**Check:** `curl https://<render-domain>/api/v1/health` →
`{"status":"ok","checks":{"postgres":"ok"}}`; the service's Logs show Alembic's
`Context impl PostgresqlImpl` line before uvicorn starts; and on GitHub, Actions → keep-alive →
**Run workflow** passes. A 503 names the failing check. Render also checks the running service: after
60 s of failures it restarts it (design §4).

## 3. Vercel — the web app

1. vercel.com → Add New → Project → import `Katlego-tech/Panelwise`.
2. **Root directory** `apps/web`. The framework (Next.js), install and build commands, and the
   functions' region (`fra1`, Frankfurt, beside the API) come from `apps/web/vercel.json`. Leave
   **Optional Integrations → Supabase** alone: it would put the secret key and Postgres strings on
   Vercel (design §4: the web gets the publishable key only), or make a second Supabase project.
   After the project exists: Settings → Build and Deployment → Root Directory → turn **off**
   "Include files outside the root directory in the Build Step". While it is on, Vercel looks for
   `packageManager` in a `package.json` at the repository root (we have none), so corepack stays
   off, an older pnpm refuses our pnpm 11 lockfile and the install fails ("Ignoring not compatible
   lockfile … Headless installation requires a pnpm-lock.yaml file"; 2026-10-16). Nothing in
   `apps/web` reads a file outside it.
3. Environment variables:

   | Variable | Value |
   |---|---|
   | `API_URL` | `https://<render-domain>` from step 2, no trailing slash. Server-side only |
   | `ENABLE_EXPERIMENTAL_COREPACK` | `1`, so Vercel uses the pnpm version pinned in `package.json` |
   | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | step 1, the **publishable** key only (the browser sign-in, from T040) |

**Check:** `curl https://<vercel-domain>/api/health` →
`{"web":"ok","api":{"status":"ok","checks":{"postgres":"ok"}}}` with HTTP 200. A 502 means Vercel
can't reach `API_URL`. The project's Settings → Functions shows the region `fra1`.

### Web first, before the API (2026-10-11)

The web deploys and signs in with no API anywhere: sign-in is Supabase's, and every page that needs
the API shows its "unavailable" state instead of failing (`apps/web/lib/api/server.ts`).
Checked on 2026-10-11 with `VERCEL=1 pnpm run build` in `apps/web`: it builds, 13 routes plus the
proxy.

1. Do step 3 with **`API_URL` left unset**. Set `ENABLE_EXPERIMENTAL_COREPACK=1` and the two
   `NEXT_PUBLIC_SUPABASE_*` values (the publishable key, never the secret one).
   `NEXT_PUBLIC_*` values are built into the pages, so set them **before** the first deploy, or
   redeploy after setting them.
2. Node.js: nothing to set. `"engines"` in `apps/web/package.json` (`>=24.18 <25`) overrides the
   project's Node.js setting (Settings → Build and Deployment, shown only once the project exists).
3. **Check, without the API:**
   - `https://<vercel-domain>/` sends you to `/sign-in`.
   - You can sign in with your own Supabase user. Sign-up is off (web.md §10), so the dashboard
     creates users.
   - `/projects` opens and says "Your screenplays can't be loaded right now. Reload the page to
     try again." (the list's no-API state).
   - `curl -i https://<vercel-domain>/api/health` answers **502**, because no API answers yet.
     That is the expected answer here, not a broken deploy.
4. **When the API is up on Render:** set `API_URL` to its URL (no trailing slash) and **redeploy**,
   since Vercel reads a changed variable only in a new deploy. Then run step 3's check: it now
   answers 200.

## When it's done

All three checks pass: T037 is done. Record the two URLs in STATUS.md § Environment & access. Every push to `main` now redeploys the web app, and the API when `services/api/**` changed; every PR gets a Vercel preview.
