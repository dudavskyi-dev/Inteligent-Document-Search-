[CmdletBinding()]
param(
    [ValidateRange(96, 300)]
    [int]$Dpi = 180,

    [string]$PdftoppmPath = ""
)

$ErrorActionPreference = "Stop"

$spikeRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $spikeRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$moduleRoot = Join-Path $spikeRoot "src"
$inputRoot = Join-Path $spikeRoot "data\inputs"
$source = Join-Path $inputRoot "01_GSA_VA_Chiller_Maintenance_Solicitation.pdf"
$scanOutput = Join-Path $inputRoot "04_GSA_Table_Scan_Fixture.pdf"
$mixedOutput = Join-Path $inputRoot "05_GSA_Mixed_Table_Fixture.pdf"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Local Python was not found. Run '.\spike\setup_parsing.ps1' first."
}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Required source PDF was not found: '$source'. See spike/data/README.md."
}

if ([string]::IsNullOrWhiteSpace($PdftoppmPath)) {
    $resolved = Get-Command "pdftoppm" -ErrorAction SilentlyContinue
    if ($null -eq $resolved) {
        throw "Poppler pdftoppm was not found on PATH. Install/provide Poppler, or pass -PdftoppmPath."
    }
    $PdftoppmPath = $resolved.Source
}
if (-not (Test-Path -LiteralPath $PdftoppmPath -PathType Leaf)) {
    throw "pdftoppm executable was not found: '$PdftoppmPath'."
}

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $moduleRoot
    & $python -m benchmark.fixture_builder `
        --source $source `
        --scan-output $scanOutput `
        --mixed-output $mixedOutput `
        --pdftoppm $PdftoppmPath `
        --dpi $Dpi
    if ($LASTEXITCODE -ne 0) {
        throw "Fixture generation failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host "Created '$scanOutput'."
Write-Host "Created '$mixedOutput'."

