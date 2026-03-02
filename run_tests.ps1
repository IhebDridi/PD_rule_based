# Run oTree tests using the venv in parent directory (..\.PD)
$ProjectRoot = $PSScriptRoot
$VenvRoot = Join-Path (Split-Path $ProjectRoot -Parent) ".PD"
$OtreeExe = Join-Path $VenvRoot "Scripts\otree.exe"

if (-not (Test-Path $OtreeExe)) {
    Write-Error "Venv not found at: $VenvRoot. Expected ..\.PD\Scripts\otree.exe"
    exit 1
}

Set-Location $ProjectRoot
& $OtreeExe test prisoners_dilemma @args
