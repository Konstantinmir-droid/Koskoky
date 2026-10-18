param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference = 'Stop'
if ((Get-Service MpsSvc).Status -ne 'Running') { throw 'Firewall service is not running' }
if (Get-NetFirewallProfile | Where-Object { $_.Enabled -ne 'True' }) { throw 'A firewall profile is disabled' }
$executables = @(Get-ChildItem -LiteralPath $Directory -Filter *.exe -Recurse)
if ($executables.Count -eq 0) { throw 'No application executables found' }
foreach ($exe in $executables) {
    $id = 'LocalDocRenamer-' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($exe.FullName))
    $rule = Get-NetFirewallRule -PolicyStore ActiveStore -Name $id
    if ($rule.Enabled -ne 'True' -or $rule.Direction -ne 'Outbound' -or $rule.Action -ne 'Block') { throw 'Outbound block is not active' }
    $filter = $rule | Get-NetFirewallApplicationFilter
    if ($filter.Program -ne $exe.FullName) { throw 'Unexpected application path' }
}
