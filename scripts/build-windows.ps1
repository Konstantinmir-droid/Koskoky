# Build-machine script. End users never install Python or OCR.
param([string]$Python = 'py', [switch]$SkipInstall, [string]$InnoSetup = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Build requires Windows x64' }
function Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" }
}
Checked { & $Python -3.11 -m venv .venv }
$P = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not $SkipInstall) {
    Checked { & $P -m pip install --upgrade pip }
    # Requires Visual Studio Build Tools with Desktop C++ on the BUILD machine only.
    $env:CMAKE_ARGS = '-DGGML_CUDA=OFF -DGGML_NATIVE=OFF -DGGML_AVX512=OFF'
    Checked { & $P -m pip install -r requirements.txt }
}
Checked { & $P scripts\preflight.py }
Checked { & $P -m unittest discover -s tests -v }
Checked { & $P -m PyInstaller --noconfirm --clean LocalDocRenamer.spec }
Copy-Item THIRD_PARTY_NOTICES.md dist\LocalDocRenamer -Force
Copy-Item README_RU.md dist\LocalDocRenamer -Force
Copy-Item scripts\block-network.ps1 dist\LocalDocRenamer -Force
New-Item dist\LocalDocRenamer\portable.flag -ItemType File -Force | Out-Null
Checked { & $P scripts\release-manifest.py dist\LocalDocRenamer }
Write-Host 'Candidate build is in dist\LocalDocRenamer. Run the Windows acceptance checklist BEFORE release.'

if (-not $InnoSetup) {
    $InnoSetup = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
}
if (-not (Test-Path -LiteralPath $InnoSetup)) { throw 'Install Inno Setup 6 on the build machine, or specify -InnoSetup path to ISCC.exe. Installer not built.' }
Checked { & $InnoSetup installer\windows.iss }
Write-Host 'Installer candidate: release\LocalDocRenamer-Setup-Windows-x64.exe. Not release-verified yet.'
