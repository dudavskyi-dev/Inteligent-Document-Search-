[CmdletBinding()]
param(
    [ValidateRange(0.0, 1.0)]
    [double]$Threshold = 0.72
)

$ErrorActionPreference = "Stop"

$spikeRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $spikeRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$moduleRoot = Join-Path $spikeRoot "src"
$parsingPointer = Join-Path $spikeRoot "results\parsing\latest.txt"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Local Python was not found at '$python'."
}
if (-not (Test-Path -LiteralPath $parsingPointer -PathType Leaf)) {
    throw "Parsing result pointer was not found at '$parsingPointer'."
}

$previousPythonPath = $env:PYTHONPATH
try {
    if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $env:PYTHONPATH = $moduleRoot
    }
    else {
        $env:PYTHONPATH = "$moduleRoot;$previousPythonPath"
    }

    & $python -m benchmark.run_table_stitching `
        --project-root $projectRoot `
        --threshold $Threshold

    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
