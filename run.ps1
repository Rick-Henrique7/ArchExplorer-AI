# ============================================================
# run.ps1 — Bootstrap and launch ArchExplorer AI on Windows.
#
# - Creates .venv if missing
# - Activates it
# - Installs dev deps if PySide6 is not importable
# - Launches `python -m app.main`
#
# Usage from PowerShell:
#   .\run.ps1
# ============================================================

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$venvDir  = Join-Path $repoRoot '.venv'
$venvPy   = Join-Path $venvDir 'Scripts\python.exe'

function Assert-Venv {
    if (-not (Test-Path $venvPy)) {
        Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Cyan
        py -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
    }
}

function Assert-Deps {
    & $venvPy -c "import PySide6" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing dev dependencies ..." -ForegroundColor Cyan
        & $venvPy -m pip install --upgrade pip | Out-Null
        & $venvPy -m pip install -r (Join-Path $repoRoot 'requirements-dev.txt')
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    }
}

Assert-Venv
Assert-Deps

Write-Host "Launching ArchExplorer AI ..." -ForegroundColor Green
& $venvPy -m app.main
