[CmdletBinding()]
param(
    [switch]$RebuildCorpus
)

$ErrorActionPreference = "Stop"

$spikeRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $spikeRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$moduleRoot = Join-Path $spikeRoot "src"
$cacheRoot = Join-Path $projectRoot ".cache"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Local Python was not found at '$python'."
}

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $moduleRoot
    }
    else {
        "$moduleRoot;$previousPythonPath"
    }
    $env:HF_HOME = Join-Path $cacheRoot "huggingface"
    $env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
    $env:TRANSFORMERS_CACHE = Join-Path $env:HF_HOME "transformers"
    $env:SENTENCE_TRANSFORMERS_HOME = Join-Path $cacheRoot "sentence-transformers"
    $env:TORCH_HOME = Join-Path $cacheRoot "torch"
    $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
    $env:TOKENIZERS_PARALLELISM = "false"

    $arguments = @(
        "-m", "benchmark.run_retrieval",
        "--project-root", $projectRoot
    )
    if ($RebuildCorpus) {
        $arguments += "--rebuild-corpus"
    }

    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
