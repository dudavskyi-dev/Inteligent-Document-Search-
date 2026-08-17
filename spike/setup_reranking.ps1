[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$spikeRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $spikeRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$cacheRoot = Join-Path $projectRoot ".cache"
$logPath = Join-Path $spikeRoot "logs\setup_reranking.log"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Local Python was not found at '$python'."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null
$env:PIP_CACHE_DIR = Join-Path $cacheRoot "pip"
$env:HF_HOME = Join-Path $cacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TRANSFORMERS_CACHE = Join-Path $env:HF_HOME "transformers"
$env:SENTENCE_TRANSFORMERS_HOME = Join-Path $cacheRoot "sentence-transformers"
$env:TORCH_HOME = Join-Path $cacheRoot "torch"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

Push-Location $spikeRoot
try {
    & $python -m pip install --editable ".[reranking]" *>&1 |
        Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE. See '$logPath'."
    }
}
finally {
    Pop-Location
}

Write-Host "Reranking dependencies were installed into the project-local .venv."
Write-Host "The cross-encoder model will be downloaded into the project-local .cache by the benchmark."
