# Zetalvx Image Lab - SDXL Edition 1.0.15: independent Windows uninstaller. Windows PowerShell 5.1+.
# Runs from TEMP, never from the app's Python. Dot-sourcing only loads functions.
param([string]$SpecPath)
$ErrorActionPreference = 'Stop'
$script:UninstallSupportRoot = $PSScriptRoot
$script:CleanupRoot = $null
$script:ReportFolder = $null
$script:RemovedCount = 0
$script:Phase = 'starting'
$script:Warnings = @()
$script:OwnPending = $false

function Test-UnderRoot([string]$Path, [string]$Root) {
    if (-not $Path -or -not $Root) { return $false }
    try {
        $P = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
        $R = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
        return $P.StartsWith($R + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
    } catch { return $false }
}
function Assert-NoLinkedAncestors([string]$Path) {
    $P = [IO.Path]::GetFullPath($Path)
    while ($P) {
        $Item = Get-Item -LiteralPath $P -Force -ErrorAction SilentlyContinue
        if ($Item -and ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw ('Linked path refused: ' + $P) }
        $Parent = [IO.Path]::GetDirectoryName($P)
        if ($Parent -eq $P) { break }
        $P = $Parent
    }
}
function Read-Installation([string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path)) { throw 'Installation path must be absolute.' }
    $Root = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if (-not $Root -or $Root -eq [IO.Path]::GetPathRoot($Path).TrimEnd([IO.Path]::DirectorySeparatorChar) -or $Root -eq $env:USERPROFILE) { throw 'Unsafe uninstall root.' }
    Assert-NoLinkedAncestors $Root
    $Marker = Join-Path $Root '.zetalvx-install.json'
    Assert-NoLinkedAncestors $Marker
    if (-not (Test-Path -LiteralPath $Marker -PathType Leaf)) { throw ('Installation identity missing. Nothing removed: ' + $Marker) }
    $M = Get-Content -LiteralPath $Marker -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($M.schema -ne 1 -or $M.product -ne 'Zetalvx Creator Studio SDXL' -or -not $M.id -or -not $M.home -or [IO.Path]::GetFullPath($M.home).TrimEnd([IO.Path]::DirectorySeparatorChar) -ne $Root) { throw 'Installation identity mismatch. Nothing removed.' }
    return [pscustomobject]@{ home = $Root; id = [string]$M.id; marker = $M }
}
function Write-JsonAtomic([string]$Path, $Data) {
    $Text = $Data | ConvertTo-Json -Depth 12
    $Tmp = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($Tmp, $Text, (New-Object Text.UTF8Encoding($false)))
        if ([IO.File]::Exists($Path)) { [IO.File]::Replace($Tmp, $Path, [System.Management.Automation.Language.NullString]::Value) }
        else { [IO.File]::Move($Tmp, $Path) }
    } finally { if ([IO.File]::Exists($Tmp)) { [IO.File]::Delete($Tmp) } }
}
function Write-CleanupProgress([string]$Phase, [string]$Detail) {
    $script:Phase = $Phase
    $Line = '[' + [DateTime]::Now.ToString('HH:mm:ss') + '] ' + $Detail
    Write-Host $Line
    if ($script:ReportFolder) {
        [IO.File]::AppendAllText((Join-Path $script:ReportFolder 'cleanup.log'), $Line + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        Write-JsonAtomic (Join-Path $script:ReportFolder 'progress.json') @{
            status='running'; phase=$Phase; detail=$Detail; removed=$script:RemovedCount;
            home=$script:CleanupRoot; updated_utc=[DateTime]::UtcNow.ToString('o'); pid=$PID
        }
    }
}
function Get-ProcessIdentity([int]$ProcessId) {
    try { return 'win-filetime-' + (Get-Process -Id $ProcessId -ErrorAction Stop).StartTime.ToUniversalTime().ToFileTimeUtc().ToString() }
    catch { return $null }
}
function Test-TrackedProcess($ProcessId, $Identity) {
    return $ProcessId -and $Identity -and ((Get-ProcessIdentity ([int]$ProcessId)) -eq [string]$Identity)
}
function Get-AppProcesses([string]$Root) {
    # Executable path and user are required. No kills by process name or port.
    $MySid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    foreach ($P in @(Get-CimInstance -ClassName Win32_Process -OperationTimeoutSec 10 -ErrorAction Stop)) {
        if ($P.ProcessId -eq $PID -or -not (Test-UnderRoot ([string]$P.ExecutablePath) $Root)) { continue }
        $Live = $null
        try {
            $Live = Get-Process -Id $P.ProcessId -ErrorAction Stop
            $Start = $Live.StartTime.ToUniversalTime().ToFileTimeUtc().ToString()
            if ($Live.Path -ne $P.ExecutablePath) { continue }
            $Owner = Invoke-CimMethod -InputObject $P -MethodName GetOwnerSid -OperationTimeoutSec 5 -ErrorAction Stop
            if ($Owner.ReturnValue -ne 0) { throw ('Cannot verify owner of PID ' + $P.ProcessId) }
            if ($Owner.Sid -ne $MySid) { continue }
            [pscustomobject]@{
                id=[int]$P.ProcessId; identity=('win-filetime-' + $Start); exe=[string]$P.ExecutablePath;
                command=[string]$P.CommandLine; parent=[int]$P.ParentProcessId
            }
        } catch {
            if (Get-Process -Id $P.ProcessId -ErrorAction SilentlyContinue) { throw }
        } finally { if ($Live) { $Live.Dispose() } }
    }
}
function Stop-VerifiedProcess($Record, [string]$Root) {
    $Live = Get-Process -Id $Record.id -ErrorAction SilentlyContinue
    if (-not $Live) { return }
    try {
        # Force acquisition of a handle; compare creation identity before terminating.
        $Handle = $Live.Handle
        $Identity = 'win-filetime-' + $Live.StartTime.ToUniversalTime().ToFileTimeUtc().ToString()
        if ($Identity -ne $Record.identity -or $Live.Path -ne $Record.exe -or -not (Test-UnderRoot $Live.Path $Root)) { return }
        Write-CleanupProgress 'stopping' ('Arresto / Stopping PID ' + $Record.id + ': ' + $Record.exe)
        $Live.Kill()
    } finally { $Live.Dispose() }
}
function Stop-LegacyUninstallRunner([string]$Root, $Spec) {
    if (-not $Spec.recover_legacy) { return }
    foreach ($P in @(Get-AppProcesses $Root)) {
        if ($P.command -match '(?:^|[\\/])scripts[\\/](?:gui_uninstall|uninstall)\.py(?:["\s]|$)') {
            Stop-VerifiedProcess $P $Root
        }
    }
}
function Stop-LegacyCleanup([string]$Root, $Old, $Spec) {
    if (-not (Test-TrackedProcess $Old.cleanup_pid $Old.cleanup_start)) { return }
    if (-not $Spec.recover_legacy -or $Old.engine -eq 'native-powershell-v1') {
        throw ('Another cleanup is active. Report: ' + $Old.report_dir)
    }
    $Folder=[IO.Path]::GetFullPath([string]$Old.report_dir)
    if (-not (Test-UnderRoot $Folder ([IO.Path]::GetTempPath())) -or (Test-UnderRoot $Folder $Root)) {
        throw 'Cannot safely identify the previous cleanup. Close its window before retrying.'
    }
    Assert-NoLinkedAncestors $Folder
    $OldSpec=Join-Path $Folder 'spec.json'; Assert-NoLinkedAncestors $OldSpec
    $Previous=Get-Content -LiteralPath $OldSpec -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Previous.installation_id -ne $Spec.installation_id -or [IO.Path]::GetFullPath([string]$Previous.home).TrimEnd([IO.Path]::DirectorySeparatorChar) -ne $Root -or $Previous.schema -eq 'zetalvx.native-uninstall.v1') {
        throw 'Previous cleanup specification could not be verified. Nothing removed.'
    }
    $PsExe=Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
    $Cim=Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId='+[int]$Old.cleanup_pid) -OperationTimeoutSec 10
    if (-not $Cim) {return}
    $ScriptPattern='(?:^|\s)-File\s+(?:"'+[regex]::Escape((Join-Path $Folder 'cleanup.ps1'))+'"|'+[regex]::Escape((Join-Path $Folder 'cleanup.ps1'))+')(?:\s|$)'
    $SpecPattern='(?:^|\s)-SpecPath\s+(?:"'+[regex]::Escape($OldSpec)+'"|'+[regex]::Escape($OldSpec)+')(?:\s|$)'
    $Owner=Invoke-CimMethod -InputObject $Cim -MethodName GetOwnerSid -OperationTimeoutSec 5
    if ($Cim.ExecutablePath -ne $PsExe -or $Cim.CommandLine -inotmatch $ScriptPattern -or $Cim.CommandLine -inotmatch $SpecPattern -or $Owner.ReturnValue -ne 0 -or $Owner.Sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
        throw 'Previous cleanup process ownership could not be verified. Nothing removed.'
    }
    $Live=Get-Process -Id $Old.cleanup_pid -ErrorAction SilentlyContinue
    if (-not $Live) {return}
    try {
        $Handle=$Live.Handle
        $Identity='win-filetime-'+$Live.StartTime.ToUniversalTime().ToFileTimeUtc().ToString()
        if ($Identity -ne $Old.cleanup_start -or $Live.Path -ne $PsExe) {throw 'Previous cleanup PID changed. Nothing removed.'}
        Write-CleanupProgress 'recovering' ('Arresto cleanup precedente verificato / Stopping verified legacy cleanup PID '+$Old.cleanup_pid)
        $Live.Kill()
        if (-not $Live.WaitForExit(5000)) {throw 'Previous cleanup did not exit.'}
    } finally {$Live.Dispose()}
}
function Get-LifecycleLocks([string]$Root, [int]$TimeoutSeconds=25) {
    $Held = New-Object 'Collections.Generic.List[IO.FileStream]'
    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    try {
        foreach ($Rel in @('install.lock','shared/run/start.lock','shared/updates/execution.lock','shared/updates/state.lock','shared/run/execution.lock')) {
            $Path = Join-Path $Root $Rel
            Assert-NoLinkedAncestors $Path
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
            $Stream = [IO.File]::Open($Path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
            $Acquired = $false
            try {
                while (-not $Acquired) {
                    try { $Stream.Lock(0,1); $Acquired=$true }
                    catch [IO.IOException] {
                        if ([DateTime]::UtcNow -ge $Deadline) { throw ('Timeout waiting for lifecycle lock: ' + $Path + '. No app files have been deleted.') }
                        Write-CleanupProgress 'waiting-lock' ('Attesa operazione / Waiting for operation: ' + $Rel)
                        Start-Sleep -Milliseconds 500
                    }
                }
                if ($Stream.Length -eq 0) { $Stream.WriteByte(0); $Stream.Flush() }
                $Held.Add($Stream)
            } catch { $Stream.Dispose(); throw }
        }
        return ,$Held
    } catch { foreach ($S in $Held) { $S.Dispose() }; throw }
}
function Stop-AppProcesses([string]$Root) {
    $Processes = @(Get-AppProcesses $Root)
    foreach ($P in $Processes) {
        if ($P.command -match '(?:^|[\\/])scripts[\\/](?:install|gui_update)\.py(?:["\s]|$)') { throw ('Installer/updater is active: PID ' + $P.id + '. Wait for it to finish.') }
    }
    Write-CleanupProgress 'stopping' ('Processi privati trovati / Private processes found: ' + $Processes.Count)
    $StatePath = Join-Path $Root 'shared/run/supervisor.json'
    if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
        Assert-NoLinkedAncestors $StatePath
        $State = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $Supervisor = @($Processes | Where-Object { $_.id -eq $State.pid -and $_.identity -eq $State.start })
        if ($Supervisor.Count) {
            Write-JsonAtomic (Join-Path $Root 'shared/run/stop-request.json') @{pid=$State.pid;start=$State.start}
            # Graceful supervisor shutdown first, then both venv redirectors and real children.
            $End = [DateTime]::UtcNow.AddSeconds(5)
            while ((Test-TrackedProcess $State.pid $State.start) -and [DateTime]::UtcNow -lt $End) { Start-Sleep -Milliseconds 250 }
        }
    }
    $End = [DateTime]::UtcNow.AddSeconds(20)
    do {
        $Processes = @(Get-AppProcesses $Root)
        if (-not $Processes.Count) { Write-CleanupProgress 'stopped' 'App e runtime arrestati / App and runtime processes stopped.'; return }
        # Snapshot includes redirectors AND real interpreters before any are terminated.
        foreach ($P in $Processes) { Stop-VerifiedProcess $P $Root }
        Start-Sleep -Milliseconds 350
    } while ([DateTime]::UtcNow -lt $End)
    $Remaining = @(Get-AppProcesses $Root)
    if ($Remaining.Count) { throw ('Processes did not stop: ' + (($Remaining | ForEach-Object { [string]$_.id + ' ' + $_.exe }) -join '; ')) }
}
function Initialize-TreeRemoval {
    if ('ZetalvxUninstall.TreeRemoval' -as [type]) { return }
    Add-Type -Path (Join-Path $script:UninstallSupportRoot 'uninstall_tree.cs')
}
function Remove-OwnedTree([string]$Path) {
    if ($Path -ne $script:CleanupRoot -and -not (Test-UnderRoot $Path $script:CleanupRoot)) { throw 'Delete path escapes installation.' }
    # A linked target is removed as a link, never followed. Its ancestors must be real.
    Assert-NoLinkedAncestors ([IO.Path]::GetDirectoryName($Path))
    $Callback = [Action[long,string]]{
        param($Count,$Current)
        $script:RemovedCount += $Count
        Write-CleanupProgress 'deleting' ('Elementi eliminati / Removed entries: ' + $script:RemovedCount + ' | ' + $Current)
    }
    $Last = $null
    for ($Attempt=1; $Attempt -le 5; $Attempt++) {
        $Removal = New-Object ZetalvxUninstall.TreeRemoval
        $Removal.DeadlineUtc = $script:DeleteDeadline
        $Removal.Progress = $Callback
        $Removal.Remove($Path)
        if ($Removal.Errors.Count -eq 0) { return }
        $Last = ($Removal.Errors -join [Environment]::NewLine)
        Write-CleanupProgress 'retrying' ('File ancora occupati / Files still blocked; retry ' + $Attempt + '/5: ' + $Last)
        if ($Attempt -lt 5) { Start-Sleep -Milliseconds (300 * $Attempt) }
    }
    throw ('Cannot remove files. Close applications/terminals using the reported paths and run UNINSTALL.cmd again.' + [Environment]::NewLine + $Last)
}
function Remove-OwnedShortcuts([string]$Root) {
    try {
        $Wsh = New-Object -ComObject WScript.Shell
        $Programs = [Environment]::GetFolderPath('Programs')
        $Desktop = [Environment]::GetFolderPath('DesktopDirectory')
        $Folders = @((Join-Path $Programs 'Zetalvx Image Lab - SDXL Edition'),(Join-Path $Programs 'Zetalvx Creator Studio'), (Join-Path $Programs 'Zetalvx SDXL'), $Desktop)
        $Names = @('Zetalvx Image Lab - SDXL Edition','Zetalvx Image Lab - SDXL Edition - LAN','Disinstalla Zetalvx Image Lab - SDXL Edition','Zetalvx Creator Studio','Zetalvx Creator Studio - LAN','Disinstalla Zetalvx Creator Studio','Zetalvx SDXL','Zetalvx SDXL - LAN')
        foreach ($Folder in $Folders) {
            foreach ($Name in $Names) {
                $File = Join-Path $Folder ($Name+'.lnk')
                if (Test-Path -LiteralPath $File -PathType Leaf) {
                    $Link = $Wsh.CreateShortcut($File)
                    $Pattern = '(?:^|\s)--home\s+(?:"'+[regex]::Escape($Root)+'"|'+[regex]::Escape($Root)+')(?:\s|$)'
                    if ((Test-UnderRoot $Link.TargetPath $Root) -or $Link.Arguments -imatch $Pattern) { Remove-Item -LiteralPath $File -Force }
                }
            }
        }
        foreach ($Folder in $Folders[0..1]) {
            if ((Test-Path -LiteralPath $Folder -PathType Container) -and @(Get-ChildItem -LiteralPath $Folder -Force).Count -eq 0) { Remove-Item -LiteralPath $Folder }
        }
    } catch { $script:Warnings += ('Shortcut cleanup: ' + $_.Exception.Message) }
}
function Remove-InstallationPayload([string]$Root, [bool]$Purge) {
    # Preserve marker and the independent retry entry until payload deletion succeeds.
    foreach ($Name in @('runtime','versions','shared/updates','shared/run','cache/uv')) {
        $Target = Join-Path $Root $Name
        $Parent=[IO.Path]::GetDirectoryName($Target)
        $LinkedParent=$false
        while ($Parent -and $Parent -ne $Root) {
            $Item=Get-Item -LiteralPath $Parent -Force -ErrorAction SilentlyContinue
            if ($Item -and ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { $LinkedParent=$true; break }
            $Parent=[IO.Path]::GetDirectoryName($Parent)
        }
        if ($LinkedParent) { continue } # purge later unlinks the top-level link; keep-data preserves it.
        Write-CleanupProgress 'deleting' ('Eliminazione / Removing: ' + $Target)
        Remove-OwnedTree $Target
    }
    if ($Purge) {
        foreach ($Item in @(Get-ChildItem -LiteralPath $Root -Force)) {
            if ($Item.Name -notin @('.zetalvx-install.json','bin','UNINSTALL.cmd','install.lock','uninstall-pending.json','install-state.json','current','previous')) { Remove-OwnedTree $Item.FullName }
        }
    }
    Remove-OwnedShortcuts $Root
    foreach ($Name in @('bin','SETUP-CODE.cmd','creator-studio-sdxl-uninstall.desktop','Disinstalla Zetalvx Creator Studio.lnk','Disinstalla Zetalvx Image Lab - SDXL Edition.lnk','uninstall.sh','UNINSTALL.cmd','current','previous','install-state.json','install.lock','uninstall-pending.json')) {
        Remove-OwnedTree (Join-Path $Root $Name)
    }
    if ($Purge) {
        $Marker = Join-Path $Root '.zetalvx-install.json'
        $Backup = Get-Content -LiteralPath $Marker -Raw -Encoding UTF8
        Remove-OwnedTree $Marker
        try {
            # Non-recursive final removal: never sweep a new/unexpected directory here.
            [IO.Directory]::Delete($Root, $false)
        } catch {
            if ((Test-Path -LiteralPath $Root -PathType Container) -and -not (Test-Path -LiteralPath $Marker)) {
                Assert-NoLinkedAncestors $Root
                [IO.File]::WriteAllText($Marker,$Backup,(New-Object Text.UTF8Encoding($false)))
            }
            throw ('Root directory still in use or not empty: ' + $Root + '. Close terminals/File Explorer using it. ' + $_.Exception.Message)
        }
        if (Test-Path -LiteralPath $Root) { throw 'Final verification failed: installation folder still exists.' }
    } else {
        foreach ($Name in @('runtime','versions','bin','install-state.json')) {
            if (Test-Path -LiteralPath (Join-Path $Root $Name)) { throw ('Final verification failed: ' + $Name + ' remains.') }
        }
    }
}
function Show-UninstallMessage([string]$Text, [bool]$Question=$false) {
    Add-Type -AssemblyName System.Windows.Forms
    if ($Question) {
        return [System.Windows.Forms.MessageBox]::Show($Text,'Zetalvx Image Lab - SDXL Edition - Disinstallazione / Uninstall',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Warning,[System.Windows.Forms.MessageBoxDefaultButton]::Button2) -eq [System.Windows.Forms.DialogResult]::Yes
    }
    [System.Windows.Forms.MessageBox]::Show($Text,'Zetalvx Image Lab - SDXL Edition - Disinstallazione / Uninstall') | Out-Null
}
function Invoke-NativeUninstall([string]$JobSpec) {
    $script:RemovedCount=0; $script:Warnings=@(); $script:OwnPending=$false; $script:CleanupRoot=$null; $script:Phase='starting'
    $Locks = $null; $Spec = $null; $Result = $null
    $script:ReportFolder = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($JobSpec))
    try {
        $Spec = Get-Content -LiteralPath $JobSpec -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Spec.schema -ne 'zetalvx.native-uninstall.v1' -or $Spec.purge_data -isnot [bool] -or $Spec.id -notmatch '^[a-f0-9]{32}$') { throw 'Invalid uninstall specification.' }
        $Installation = Read-Installation $Spec.home
        $Root = $Installation.home; $script:CleanupRoot = $Root
        if ($Installation.id -ne $Spec.installation_id) { throw 'Installation changed after confirmation.' }
        if ($script:ReportFolder -eq $Root -or (Test-UnderRoot $script:ReportFolder $Root)) { throw 'Cleanup must run outside the installation.' }
        Set-Location -LiteralPath $script:ReportFolder
        [Environment]::CurrentDirectory = $script:ReportFolder
        Write-CleanupProgress 'validating' ('Cartella installata / Installed folder: ' + $Root)
        Write-CleanupProgress 'validating' ('Rimozione completa / Delete personal data: ' + $Spec.purge_data)
        Initialize-TreeRemoval
        $PendingPath = Join-Path $Root 'uninstall-pending.json'
        Assert-NoLinkedAncestors $PendingPath
        if (Test-Path -LiteralPath $PendingPath -PathType Leaf) {
            $Old = Get-Content -LiteralPath $PendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($Old.installation_id -ne $Installation.id) { throw 'Pending uninstall belongs to another installation.' }
            if ($Old.id -ne $Spec.id) { Stop-LegacyCleanup $Root $Old $Spec }
        }
        # Only a locally confirmed recovery can terminate an old Python uninstaller.
        Stop-LegacyUninstallRunner $Root $Spec
        $Locks = Get-LifecycleLocks $Root
        # Recheck under the install lock so two concurrent native workers cannot run.
        if (Test-Path -LiteralPath $PendingPath -PathType Leaf) {
            $Old = Get-Content -LiteralPath $PendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($Old.installation_id -ne $Installation.id) { throw 'Pending uninstall identity mismatch.' }
            if ($Old.id -ne $Spec.id -and (Test-TrackedProcess $Old.cleanup_pid $Old.cleanup_start)) { throw ('Another cleanup is active. Report: ' + $Old.report_dir) }
            if ($Old.id -ne $Spec.id -and -not $Spec.recover_legacy -and (Test-TrackedProcess $Old.pid $Old.process_start)) { throw 'Another uninstall runner is active.' }
        }
        Write-JsonAtomic $PendingPath @{
            id=$Spec.id; installation_id=$Installation.id; status='cleanup'; engine='native-powershell-v1';
            cleanup_pid=$PID; cleanup_start=(Get-ProcessIdentity $PID); report_dir=$script:ReportFolder;
            created_at=([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
        }
        $script:OwnPending = $true
        # Allow the browser's accepted response to arrive before stopping the web server.
        Start-Sleep -Seconds 2
        Stop-AppProcesses $Root
        foreach ($Lock in $Locks) { $Lock.Dispose() }; $Locks=$null
        $script:DeleteDeadline = [DateTime]::UtcNow.AddMinutes(10)
        Remove-InstallationPayload $Root $Spec.purge_data
        $Result = @{ok=$true;home=$Root;data_preserved=(-not $Spec.purge_data);external_paths_deleted=$false;removed=$script:RemovedCount;warnings=$script:Warnings;engine='native-powershell-v1'}
        Write-CleanupProgress 'completed' 'Disinstallazione completata e verificata / Uninstall completed and verified.'
    } catch {
        $Message = $_.Exception.Message
        $Result = @{ok=$false;error=$Message;home=$script:CleanupRoot;phase=$script:Phase;removed=$script:RemovedCount;external_paths_deleted=$false;data_preserved=$null;note='Removal may be partial. Review cleanup.log and rerun the extracted UNINSTALL.cmd.'}
        Write-CleanupProgress 'failed' ('ERRORE / ERROR: ' + $Message)
        if ($script:OwnPending -and $script:CleanupRoot) {
            $PendingPath = Join-Path $script:CleanupRoot 'uninstall-pending.json'
            if (Test-Path -LiteralPath $PendingPath -PathType Leaf) {
                try {
                    $State = Get-Content -LiteralPath $PendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($State.id -eq $Spec.id -and $State.cleanup_pid -eq $PID) { [IO.File]::Delete($PendingPath) }
                } catch { }
            }
        }
    } finally { if ($Locks) { foreach ($Lock in $Locks) { $Lock.Dispose() } } }
    $Report = Join-Path $script:ReportFolder 'result.json'
    Write-JsonAtomic $Report $Result
    Write-JsonAtomic (Join-Path $script:ReportFolder 'progress.json') @{status=($(if($Result.ok){'completed'}else{'failed'}));phase=$script:Phase;removed=$script:RemovedCount;home=$script:CleanupRoot;report=$Report;updated_utc=[DateTime]::UtcNow.ToString('o')}
    if ($Result.ok) {
        $Message = 'Disinstallazione completata / Uninstall complete.' + [Environment]::NewLine
        if ($Result.data_preserved) { $Message += 'Dati personali CONSERVATI / Personal data KEPT in: ' + $script:CleanupRoot }
        else { $Message += 'Cartella installata ELIMINATA / Installed folder DELETED: ' + $script:CleanupRoot }
    } else { $Message = 'Disinstallazione NON completata / Uninstall FAILED.' + [Environment]::NewLine + $Result.error }
    $Message += [Environment]::NewLine + [Environment]::NewLine + 'Report: ' + $Report
    Write-Host $Message
    if ($Spec -and $Spec.gui) { try { Show-UninstallMessage $Message } catch { Write-Host $_.Exception.Message } }
    if ($Result.ok) { return 0 }; return 1
}
if ($MyInvocation.InvocationName -ne '.') {
    if (-not $SpecPath) { Write-Error 'Use UNINSTALL.cmd. A confirmed external job specification is required.'; exit 2 }
    exit (Invoke-NativeUninstall $SpecPath)
}
