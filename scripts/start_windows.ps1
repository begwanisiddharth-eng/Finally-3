# Start the FinAlly backend (and build the frontend if present). See PLAN.md section 11.
# Idempotent: safe to run repeatedly. Pass --build to force a frontend rebuild.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PidFile = if ($env:FINALLY_PID_FILE) { $env:FINALLY_PID_FILE } else { Join-Path $RepoRoot ".finally.pid" }
$Port = if ($env:PORT) { $env:PORT } else { "8000" }
$ForceBuild = $args -contains "--build"

# --- .env bootstrap ---
$EnvFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $RepoRoot ".env.example") $EnvFile
    Write-Host "Created .env from .env.example"
}

# --- GROQ_API_KEY check (skipped under LLM_MOCK=true) ---
function Get-EnvValue($key) {
    $line = Get-Content $EnvFile | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
    if ($line) { ($line -replace "^$key=", "").Trim() } else { "" }
}
$llmMock = Get-EnvValue "LLM_MOCK"
if ($llmMock.ToLower() -ne "true") {
    $groq = Get-EnvValue "GROQ_API_KEY"
    if ([string]::IsNullOrWhiteSpace($groq) -or $groq -eq "your-groq-api-key-here") {
        Write-Warning "GROQ_API_KEY is not set in .env; chat will fail unless LLM_MOCK=true."
    }
}

# --- Already-running check ---
if (Test-Path $PidFile) {
    $existingPid = (Get-Content $PidFile).Trim()
    $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "FinAlly already running (PID $existingPid) at http://127.0.0.1:$Port"
        exit 0
    }
    Remove-Item $PidFile -Force  # stale
}

# --- Frontend build (only if a frontend project exists) ---
$Frontend = Join-Path $RepoRoot "frontend"
$FrontendOut = Join-Path $Frontend "out"
if (Test-Path (Join-Path $Frontend "package.json")) {
    if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
        Push-Location $Frontend; npm install; Pop-Location
    }
    if ($ForceBuild -or -not (Test-Path $FrontendOut)) {
        Push-Location $Frontend; npm run build; Pop-Location
    }
} else {
    Write-Warning "No frontend/ project found; backend will serve the API only."
}

# --- Backend deps ---
$Backend = Join-Path $RepoRoot "backend"
Push-Location $Backend; uv sync; Pop-Location

# --- Launch uvicorn directly and record its PID ---
$proc = Start-Process -FilePath "uv" `
    -ArgumentList "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port `
    -WorkingDirectory $Backend -PassThru
$proc.Id | Out-File -FilePath $PidFile -Encoding ascii

# --- Wait for health ---
$healthy = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($r.status -eq "ok") { $healthy = $true; break }
    } catch {}
}
if ($healthy) {
    Write-Host "FinAlly is running at http://127.0.0.1:$Port (PID $($proc.Id))"
} else {
    Write-Warning "Backend did not report healthy in time; check the logs."
    exit 1
}
