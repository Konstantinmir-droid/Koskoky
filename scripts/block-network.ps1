# Run elevated on the END USER computer if OS-enforced egress blocking is required.
# The application itself does not require admin rights.
param([string]$Directory = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$executables = Get-ChildItem -LiteralPath $Directory -Filter *.exe -Recurse
foreach ($exe in $executables) {
    $id = 'LocalDocRenamer-' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($exe.FullName))
    if (-not (Get-NetFirewallRule -Name $id -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name $id -DisplayName ('LocalDocRenamer offline: ' + $exe.Name) -Direction Outbound -Program $exe.FullName -Action Block -Profile Any | Out-Null
    }
}
Write-Host 'Outbound connections blocked for all EXE files in this folder. Repeat after moving the portable folder.'
