[CmdletBinding()]
param(
    [string]$PythonCommand = "py",
    [string]$PythonVersionArgument = "-3.12"
)

$ErrorActionPreference = "Stop"

$spikeRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $spikeRoot
$venvRoot = Join-Path $projectRoot ".venv"
$python = Join-Path $venvRoot "Scripts\python.exe"
$cacheRoot = Join-Path $projectRoot ".cache"
$logPath = Join-Path $spikeRoot "logs\setup_parsing.log"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null
New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $venvArguments = @()
    if (-not [string]::IsNullOrWhiteSpace($PythonVersionArgument)) {
        $venvArguments += $PythonVersionArgument
    }
    $venvArguments += @("-m", "venv", $venvRoot)

    & $PythonCommand @venvArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the project-local virtual environment with '$PythonCommand'."
    }
}

$env:PIP_CACHE_DIR = Join-Path $cacheRoot "pip"
$env:HF_HOME = Join-Path $cacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TRANSFORMERS_CACHE = Join-Path $env:HF_HOME "transformers"
$env:TORCH_HOME = Join-Path $cacheRoot "torch"
$env:PADDLE_HOME = Join-Path $cacheRoot "paddle"
$env:PADDLE_PDX_CACHE_HOME = Join-Path $cacheRoot "paddlex"
$env:DOCLING_ARTIFACTS_PATH = Join-Path $cacheRoot "docling"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

Push-Location $spikeRoot
try {
    & $python -m pip install --editable ".[docling,paddle,dev]" *>&1 |
        Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE. See '$logPath'."
    }
}
finally {
    Pop-Location
}

Write-Host "Parsing dependencies were installed into '$venvRoot'."
Write-Host "Package and model caches are configured under '$cacheRoot'."

