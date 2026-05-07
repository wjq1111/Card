param(
    [string]$Name = "TexasHoldemOnline"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python tools\generate_grpc.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $Name `
    --collect-submodules grpc `
    --collect-submodules google.protobuf `
    --collect-submodules proto_gen `
    client\main.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Build complete: dist\$Name.exe"
