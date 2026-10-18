param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference = 'Stop'
foreach ($exe in Get-ChildItem -LiteralPath $Directory -Filter *.exe -Recurse) {
    $id = 'LocalDocRenamer-' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($exe.FullName))
    $rule = Get-NetFirewallRule -Name $id -ErrorAction SilentlyContinue
    if ($rule) { $rule | Remove-NetFirewallRule }
}
