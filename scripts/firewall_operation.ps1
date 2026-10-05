$ErrorActionPreference='Stop'
function Snapshot($rule) {
 $pf=$rule|Get-NetFirewallPortFilter
 $af=$rule|Get-NetFirewallApplicationFilter
 $addr=$rule|Get-NetFirewallAddressFilter
 $svc=$rule|Get-NetFirewallServiceFilter
 $iface=$rule|Get-NetFirewallInterfaceFilter
 $itype=$rule|Get-NetFirewallInterfaceTypeFilter
 $sec=$rule|Get-NetFirewallSecurityFilter
 [ordered]@{
  name=$rule.Name;display=$rule.DisplayName;group=$rule.Group;description=$rule.Description
  direction=$rule.Direction.ToString();action=$rule.Action.ToString();profile=$rule.Profile.ToString()
  edge=$rule.EdgeTraversalPolicy.ToString();program=$af.Program;package=$af.Package
  protocol=$pf.Protocol.ToString();local_port=@($pf.LocalPort);remote_port=@($pf.RemotePort)
  local_address=@($addr.LocalAddress);remote_address=@($addr.RemoteAddress)
  service=$svc.Service;interface=@($iface.InterfaceAlias);interface_type=$itype.InterfaceType.ToString()
  authentication=$sec.Authentication.ToString();encryption=$sec.Encryption.ToString()
  override=[string]$sec.OverrideBlockRules;local_user=[string]$sec.LocalUser
  remote_user=[string]$sec.RemoteUser;remote_machine=[string]$sec.RemoteMachine
 }
}
function Save-Journal {
 $script:J.updated_at=[DateTime]::UtcNow.ToString('o')
 $tmp=$Journal+'.tmp'
 $script:J|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $tmp -Encoding UTF8
 Move-Item -LiteralPath $tmp -Destination $Journal -Force
}
function Equal-Snapshot($a,$b) {
 # Round trip both to ordered property bags in the same schema.
 foreach($key in $a.Keys) {
  $av=$a[$key]|ConvertTo-Json -Depth 6 -Compress
  $bv=$b.$key|ConvertTo-Json -Depth 6 -Compress
  if($av -cne $bv){return $false}
 }
 return $true
}
try {
 if($Operation -eq 'configure') {
  $script:J=[ordered]@{schema=1;operation='configure';program=$Program;port=$Port;state='planned';created_rule=$null;created_rule_enabled='';disabled=@();updated_at=''}
  Save-Journal
  $existing=Get-NetFirewallRule -Name $ManagedName -ErrorAction SilentlyContinue
  if($existing){throw 'A managed firewall rule with this identifier already exists; no overwrite.'}
  $r=New-NetFirewallRule -Name $ManagedName -DisplayName 'Zetalvx Creator Studio LAN' -Group 'Zetalvx managed LAN' -Description $ManagedName -Program $Program -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Profile Any
  $script:J.created_rule=Snapshot $r;$script:J.created_rule_enabled=$r.Enabled.ToString();Save-Journal
  if($DisableConflicts) {
   $rules=@(Get-NetFirewallApplicationFilter |Where-Object {$_.Program -ieq $Program}|ForEach-Object {
     Get-NetFirewallRule -AssociatedNetFirewallApplicationFilter $_ |Where-Object {
       $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' -and $_.Profile.ToString() -match 'Public|Any'
     }
   })
   foreach($r in $rules) {
    # Store the full relevant rule fingerprint BEFORE touching a pre-existing block.
    $entry=[ordered]@{snapshot=(Snapshot $r);changed=$false}
    $script:J.disabled+=@($entry);Save-Journal
    $r|Disable-NetFirewallRule
    $entry.changed=$true;Save-Journal
   }
  }
  $script:J.state='complete';Save-Journal
  [ordered]@{ok=$true;disabled_blocks=@($script:J.disabled|ForEach-Object {$_.snapshot.name});journal=$Journal}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Result -Encoding UTF8
 } else {
  $script:J=Get-Content -LiteralPath $Journal -Raw|ConvertFrom-Json
  if($script:J.schema -ne 1 -or $script:J.state -eq 'restored'){throw 'Invalid or already restored firewall journal.'}
  $restored=@();$skipped=@()
  foreach($entry in $script:J.disabled) {
   if(-not $entry.changed){continue}
   $r=Get-NetFirewallRule -Name $entry.snapshot.name -ErrorAction SilentlyContinue
   if(-not $r){$skipped+=@($entry.snapshot.name+' (missing)');continue}
   $now=Snapshot $r
   if($r.Enabled -eq 'False' -and (Equal-Snapshot $now $entry.snapshot)) {
    $r|Enable-NetFirewallRule;$restored+=@($r.Name)
   } else {$skipped+=@($r.Name+' (already enabled or changed since configuration)')}
  }
  if($script:J.created_rule) {
   $r=Get-NetFirewallRule -Name $script:J.created_rule.name -ErrorAction SilentlyContinue
   if($r -and $r.Enabled.ToString() -eq $script:J.created_rule_enabled -and (Equal-Snapshot (Snapshot $r) $script:J.created_rule)){$r|Remove-NetFirewallRule}
   elseif($r){$skipped+=@($r.Name+' (changed; not removed)')}
  }
  $script:J.state='restored';Save-Journal
  [ordered]@{ok=$true;restored=$restored;skipped=$skipped;journal=$Journal}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Result -Encoding UTF8
 }
 exit 0
} catch {
 if($script:J -and $Operation -eq 'configure'){$script:J.state='failed';try{Save-Journal}catch{}}
 [ordered]@{ok=$false;error=$_.Exception.Message;journal=$Journal}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Result -Encoding UTF8
 exit 1
}
