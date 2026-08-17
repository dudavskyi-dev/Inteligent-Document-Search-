[CmdletBinding()]
param(
    [ValidateSet("all", "hybrid")]
    [string]$Only = "all",

    [ValidateRange(96, 300)]
    [int]$Dpi = 180
)

$ErrorActionPreference = "Stop"

$spikeRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $spikeRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$moduleRoot = Join-Path $spikeRoot "src"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Local Python was not found at '$python'. Run '.\spike\setup_parsing.ps1' first."
}

$requiredInputs = @(
    (Join-Path $spikeRoot "data\inputs\04_GSA_Table_Scan_Fixture.pdf"),
    (Join-Path $spikeRoot "data\inputs\05_GSA_Mixed_Table_Fixture.pdf")
)

foreach ($inputPath in $requiredInputs) {
    if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
        throw "Required benchmark input was not found: '$inputPath'. Run '.\spike\build_parsing_fixtures.ps1' first."
    }
}

$previousPythonPath = $env:PYTHONPATH
try {
    if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $env:PYTHONPATH = $moduleRoot
    }
    else {
        $env:PYTHONPATH = "$moduleRoot;$previousPythonPath"
    }

    & $python -m benchmark.run_parsing_benchmark `
        --project-root $projectRoot `
        --only $Only `
        --dpi $Dpi

    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
