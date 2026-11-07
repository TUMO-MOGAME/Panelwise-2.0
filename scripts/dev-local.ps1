# Panelwise 2.0, everything on this laptop: Postgres (Docker), QVAC's model server, the API and the
# web app, each in its own window. No Supabase, no cloud model. Run from the repo root:
#
#   powershell -ExecutionPolicy Bypass -File scripts\dev-local.ps1
#
# Then open http://localhost:3000. Close the windows (and `docker compose stop postgres`) to stop.
# Needs: Docker Desktop running, fnm with Node 22.21.1 (QVAC) and Node 24 (web), uv, pnpm.

#   -TextOnly   read, extract and plan only: no drawing (e.g. before FLUX.2 klein is downloaded)

param([switch]$TextOnly)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# Ports: 5433 and 11435 because a Windows Postgres and Ollama hold the defaults on this laptop.
$pgPort = 5433
$qvacPort = 11435

# --- Preflight: what stopped earlier runs, caught before anything starts ----------------------
# A port held by something else (another project's dev server on 3000) makes the web app move to
# 3001 or the API fail; stop here and name what holds it.
foreach ($port in 3000, 8000) {
  $held = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($held) {
    $holder = Get-CimInstance Win32_Process -Filter "ProcessId=$($held[0].OwningProcess)"
    Write-Host "Port $port is in use by $($holder.Name): $($holder.CommandLine)" -ForegroundColor Red
    Write-Host "Stop it (or close Panelwise's old windows) and run this again." -ForegroundColor Red
    exit 1
  }
}
# Docker Desktop must be up for Postgres; start it and wait for its engine.
cmd /c "docker info >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
  Write-Host "Starting Docker Desktop..."
  Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep 2
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { break }
  }
  if ($LASTEXITCODE -ne 0) { Write-Host "Docker did not start." -ForegroundColor Red; exit 1 }
}
# Memory: Qwen3 4B needs ~3.6 GB; FLUX.2 [klein] with its encoder ~6 GB (the renderer unloads the
# text model before drawing, so not both). A warning, not a stop: QVAC's own check decides.
$freeGb = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
$needGb = if ($TextOnly) { 4 } else { 7 }
if ($freeGb -lt $needGb) {
  Write-Host ("Only {0:N1} GB of RAM is free; about {1} GB is needed. Close browsers or other dev servers first." -f $freeGb, $needGb) -ForegroundColor Yellow
}

# One secret shared by the web server and the API, new each run (local mode, no sign-in).
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = -join ($bytes | ForEach-Object { $_.ToString("x2") })

$env:POSTGRES_HOST_PORT = "$pgPort"
docker compose -f "$root\docker-compose.yml" up -d --wait postgres

# Every model call goes to QVAC on this machine. Local mode itself drops every cloud key a .env
# may carry (Nebius, fal.ai, Supabase) and refuses a model server or database elsewhere
# (app/core/config.py): `$env:X = ''` would not do it, as PowerShell deletes the variable instead.
# Both text tiers on Qwen3 4B (eval/README.md compares it with 1.7B); one loaded model serves
# both. One call at a time, as one local server answers one at a time.
$apiEnv = @"
`$env:DATABASE_URL = 'postgresql+asyncpg://panelwise:panelwise@localhost:$pgPort/panelwise'
`$env:PANELWISE_LOCAL_TOKEN = '$token'
`$env:NEBIUS_BASE_URL = 'http://127.0.0.1:$qvacPort/v1'
`$env:NEBIUS_MODEL_FAST = 'qwen3-4b'
`$env:NEBIUS_MODEL_REASONING = 'qwen3-4b'
`$env:LLM_CONCURRENCY = '1'
`$env:LLM_THINKING_FIELD = 'reasoning_budget'
`$env:LLM_REQUEST_TIMEOUT_S = '900'
"@
# Drawing: FLUX.2 [klein] through services/qvac-draw (the QVAC SDK, port 11436), one frame at a
# time. `qvac serve` drops `steps` and `cfg_scale`, so it drew klein at 20 steps with CFG: 6.8 min
# a 512x288 frame. At klein's 4 steps, no CFG: 38 s at 512x288, 2.0 min at 848x480 (2026-11-07).
$drawPort = 11436
if (-not $TextOnly) { $apiEnv += "; `$env:QVAC_DRAW_MODEL = 'draw'; `$env:QVAC_DRAW_URL = 'http://127.0.0.1:$drawPort/v1'; `$env:FAL_CONCURRENCY = '1'; `$env:QVAC_DRAW_MAX_PIXELS = '147456'; `$env:QVAC_DRAW_TIMEOUT_S = '900'" }

# Each window also writes its output to .local-data\logs\{qvac,api,web}.log, to follow a run.
# cmd merges stderr into stdout first, so PowerShell 5.1 copies plain lines, not error records.
$logs = "$root\.local-data\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
function Tee-Log($name) { "2>&1\`" | Tee-Object -FilePath '$logs\$name.log' -Append" }

$qvacUp = $false
try { $qvacUp = (Invoke-WebRequest "http://127.0.0.1:$qvacPort/v1/models" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
if (-not $qvacUp) {
  Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command",
    "fnm env --shell powershell | Out-String | Invoke-Expression; fnm use 22.21.1; cmd /c \`"qvac serve --openai --port $qvacPort $(Tee-Log qvac)"
}

$drawUp = $false
try { $drawUp = (Invoke-WebRequest "http://127.0.0.1:$drawPort/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
if (-not $TextOnly -and -not $drawUp) {
  if (-not (Test-Path "$root\services\qvac-draw\node_modules\@qvac\sdk")) {
    Write-Host "Installing the QVAC SDK for the drawing server (once)..."
    cmd /c "cd /d `"$root\services\qvac-draw`" && fnm exec --using 22.21.1 npm install --no-audit --no-fund"
  }
  # From the repo root: the drawing server reads the `draw` alias of ./qvac.config.json.
  Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command",
    "fnm env --shell powershell | Out-String | Invoke-Expression; fnm use 22.21.1; `$env:QVAC_DRAW_PORT = '$drawPort'; cmd /c \`"node services\qvac-draw\server.mjs $(Tee-Log draw)"
}

Start-Process powershell -WorkingDirectory "$root\services\api" -ArgumentList "-NoExit", "-Command",
  "$apiEnv; `$env:PYTHONUNBUFFERED = '1'; uv run alembic upgrade head; cmd /c \`"uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 $(Tee-Log api)"

Start-Process powershell -WorkingDirectory "$root\apps\web" -ArgumentList "-NoExit", "-Command",
  "`$env:PANELWISE_LOCAL_TOKEN = '$token'; `$env:API_URL = 'http://localhost:8000'; cmd /c \`"pnpm dev $(Tee-Log web)"

Write-Host "Starting. Open http://localhost:3000 in a few seconds (the first model call loads Qwen3)."
