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
if (-not $TextOnly) { $apiEnv += "; `$env:QVAC_DRAW_MODEL = 'draw'" }

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

Start-Process powershell -WorkingDirectory "$root\services\api" -ArgumentList "-NoExit", "-Command",
  "$apiEnv; `$env:PYTHONUNBUFFERED = '1'; uv run alembic upgrade head; cmd /c \`"uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 $(Tee-Log api)"

Start-Process powershell -WorkingDirectory "$root\apps\web" -ArgumentList "-NoExit", "-Command",
  "`$env:PANELWISE_LOCAL_TOKEN = '$token'; `$env:API_URL = 'http://localhost:8000'; cmd /c \`"pnpm dev $(Tee-Log web)"

Write-Host "Starting. Open http://localhost:3000 in a few seconds (the first model call loads Qwen3)."
