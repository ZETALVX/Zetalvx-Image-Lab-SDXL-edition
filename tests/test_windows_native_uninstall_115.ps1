# Native Windows integration tests. Only isolated TEMP fixtures are removed.
# No installed user application, real account or model directory is used.
$ErrorActionPreference='Stop'
$Source=Split-Path -Parent $PSScriptRoot
. (Join-Path $Source 'scripts/uninstall_windows.ps1')
$Base=Join-Path ([IO.Path]::GetTempPath()) ('zetalvx-uninstall-tests-'+[Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($Base) | Out-Null
$Results=@();$Processes=@();$OpenFile=$null
function Assert-True([bool]$Condition,[string]$Message) {if (-not $Condition){throw $Message}}
function New-Fixture([string]$Name,[bool]$Purge) {
    $AppRoot=Join-Path $Base $Name;[IO.Directory]::CreateDirectory($AppRoot)|Out-Null
    foreach($Dir in @('runtime','versions/1.0.14','bin','models','shared/config','shared/run')){[IO.Directory]::CreateDirectory((Join-Path $AppRoot $Dir))|Out-Null}
    Write-JsonAtomic (Join-Path $AppRoot '.zetalvx-install.json') @{schema=1;product='Zetalvx Creator Studio SDXL';id=$Name;home=$AppRoot}
    Write-JsonAtomic (Join-Path $AppRoot 'install-state.json') @{current='1.0.14';previous=$null}
    foreach($Rel in @('runtime/dummy.txt','versions/1.0.14/app.py','bin/retry.txt','models/keep.safetensors','shared/config/account.json')){[IO.File]::WriteAllText((Join-Path $AppRoot $Rel),'fixture only')}
    $Folder=Join-Path $Base ($Name+'-report');[IO.Directory]::CreateDirectory($Folder)|Out-Null
    $Spec=Join-Path $Folder 'spec.json'
    Write-JsonAtomic $Spec @{schema='zetalvx.native-uninstall.v1';id=[Guid]::NewGuid().ToString('N');home=$AppRoot;installation_id=$Name;purge_data=$Purge;gui=$false;recover_legacy=$false}
    return [pscustomobject]@{root=$AppRoot;spec=$Spec;report=$Folder}
}
function Start-FixtureProcess([string]$Folder) {
    [IO.Directory]::CreateDirectory($Folder)|Out-Null
    $Exe=Join-Path $Folder 'fixture-cmd.exe';Copy-Item -LiteralPath $env:ComSpec -Destination $Exe
    $Info=New-Object Diagnostics.ProcessStartInfo
    $Info.FileName=$Exe;$Info.Arguments='/d /q /k';$Info.UseShellExecute=$false
    $Info.RedirectStandardInput=$true;$Info.RedirectStandardOutput=$true;$Info.CreateNoWindow=$true
    $Proc=[Diagnostics.Process]::Start($Info)
    Start-Sleep -Milliseconds 250
    Assert-True (-not $Proc.HasExited) 'Fixture process failed to start.'
    return $Proc
}
try {
    # Only private executables are stopped; a same-name external executable remains alive.
    $Keep=New-Fixture 'keep' $false
    $Own=Start-FixtureProcess (Join-Path $Keep.root 'runtime');$Processes+=,$Own
    $Other=Start-FixtureProcess (Join-Path $Base 'keep-backup');$Processes+=,$Other
    $Rc=Invoke-NativeUninstall $Keep.spec
    Assert-True ($Rc -eq 0) 'Keep-data uninstall failed.'
    Assert-True ($Own.WaitForExit(5000)) 'Owned fixture process remains alive.'
    Assert-True (-not $Other.HasExited) 'Unrelated same-name process was terminated.'
    Assert-True (Test-Path -LiteralPath (Join-Path $Keep.root 'models/keep.safetensors')) 'User data was not preserved.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $Keep.root 'runtime'))) 'Runtime still exists.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $Keep.root 'bin'))) 'Commands still exist.'
    $Results+=@{test='keep_data_and_process_isolation';ok=$true}

    # A junction must be unlinked, not traversed, even during a complete removal.
    $Purge=New-Fixture 'purge' $true
    $External=Join-Path $Base 'external-models';[IO.Directory]::CreateDirectory($External)|Out-Null
    $Sentinel=Join-Path $External 'NEVER_DELETE.txt';[IO.File]::WriteAllText($Sentinel,'external data')
    $Junction=Join-Path $Purge.root 'models/linked'
    & $env:ComSpec /d /c "mklink /J `"$Junction`" `"$External`"" | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) 'Could not create junction fixture.'
    $Rc=Invoke-NativeUninstall $Purge.spec
    Assert-True ($Rc -eq 0) 'Full uninstall failed.'
    Assert-True (-not (Test-Path -LiteralPath $Purge.root)) 'Full uninstall left the app folder.'
    Assert-True (Test-Path -LiteralPath $Sentinel) 'External junction target was deleted.'
    $Results+=@{test='purge_and_external_junction';ok=$true}

    # Held file causes a visible failure, preserves the marker/retry entry, then retry succeeds.
    $Locked=New-Fixture 'locked' $true
    $File=Join-Path $Locked.root 'runtime/locked.bin'
    $OpenFile=[IO.File]::Open($File,[IO.FileMode]::Create,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $Rc=Invoke-NativeUninstall $Locked.spec
    Assert-True ($Rc -ne 0) 'Locked file was reported as success.'
    Assert-True (Test-Path -LiteralPath (Join-Path $Locked.root '.zetalvx-install.json')) 'Failure deleted the retry identity.'
    Assert-True (Test-Path -LiteralPath (Join-Path $Locked.root 'bin/retry.txt')) 'Failure deleted retry entry too early.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $Locked.root 'uninstall-pending.json'))) 'Failure left maintenance mode locked.'
    $OpenFile.Dispose();$OpenFile=$null
    $Rc=Invoke-NativeUninstall $Locked.spec
    Assert-True ($Rc -eq 0) 'Retry after releasing the file failed.'
    Assert-True (-not (Test-Path -LiteralPath $Locked.root)) 'Retry left the installed directory.'
    $Results+=@{test='blocked_file_and_retry';ok=$true}

    # Missing marker must fail before deleting any application-looking files.
    $Invalid=New-Fixture 'invalid' $true
    [IO.File]::Delete((Join-Path $Invalid.root '.zetalvx-install.json'))
    $Rc=Invoke-NativeUninstall $Invalid.spec
    Assert-True ($Rc -ne 0) 'Missing identity was accepted.'
    Assert-True (Test-Path -LiteralPath (Join-Path $Invalid.root 'runtime/dummy.txt')) 'Unidentified root was changed.'
    $Results+=@{test='missing_identity_refused';ok=$true}

    @{ok=$true;native_windows=$true;tests=$Results;report_folder=$Base}|ConvertTo-Json -Depth 5|Write-Host
    exit 0
} catch {
    Write-Host ('[NATIVE TEST FAILED] '+$_.Exception.Message)
    Write-Host ('Fixtures and logs preserved at: '+$Base)
    exit 1
} finally {
    if($OpenFile){$OpenFile.Dispose()}
    foreach($Proc in $Processes){try{if(-not $Proc.HasExited){$Proc.Kill();$Proc.WaitForExit(5000)|Out-Null};$Proc.Dispose()}catch{}}
    # Test logs intentionally remain in TEMP for inspection; no broad recursive cleanup.
}
