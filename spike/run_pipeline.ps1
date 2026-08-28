[CmdletBinding()]
param(
    # Not named -Input: $Input is a reserved PowerShell automatic variable and never binds.
    [string]$InputPdf = "spike\data\inputs\03_NASA_Fastener_Procurement_Standard.pdf",
    [string]$Model,
    [int]$TopK = 3,
    [int]$CandidateK = 10,
    [int]$MaxLlmPages = 12,
    [int]$Dpi = 180,
    [switch]$NoRerank,
    [switch]$DryRun,
    [switch]$RebuildParse
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

# Load OPENROUTER_API_KEY / OPENROUTER_MODEL from a gitignored .env when present.
$envFile = Join-Path $projectRoot ".env"
if (Test-Path -LiteralPath $envFile -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $separator = $trimmed.IndexOf("=")
        if ($separator -lt 1) { continue }
        $name = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim().Trim('"')
        if ($value -ne "") {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
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
        "-m", "benchmark.run_pipeline",
        "--project-root", $projectRoot,
        "--input", $InputPdf,
        "--top-k", $TopK,
        "--candidate-k", $CandidateK,
        "--max-llm-pages", $MaxLlmPages,
        "--dpi", $Dpi
    )
    if ($Model) { $arguments += @("--model", $Model) }
    if ($NoRerank) { $arguments += "--no-rerank" }
    if ($DryRun) { $arguments += "--dry-run" }
    if ($RebuildParse) { $arguments += "--rebuild-parse" }

    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
