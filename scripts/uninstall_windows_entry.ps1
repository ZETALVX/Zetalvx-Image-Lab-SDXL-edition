# Native local entry. Also works for an interrupted 1.0.14 installation.
# This script never imports Python or depends on versions/current/bin/manage.py.
$ErrorActionPreference='Stop'
$Options=@($args)
$Root=if ($env:SDXL_STUDIO_HOME) {$env:SDXL_STUDIO_HOME} else {Join-Path $env:LOCALAPPDATA 'CreatorStudioSDXL'}
$Purge=$false; $Yes=$false; $Gui=$false; $Plan=$false
try {
    for ($I=0; $I -lt $Options.Count; $I++) {
        switch -Regex ($Options[$I]) {
            '^--home$' { $I++; if ($I -ge $Options.Count) {throw 'Missing --home value.'}; $Root=$Options[$I]; break }
            '^--home=' { $Root=$Options[$I].Substring(7); break }
            '^--purge-data$' { $Purge=$true; break }
            '^--yes$' { $Yes=$true; break }
            '^--gui$' { $Gui=$true; break }
            '^--plan$' { $Plan=$true; break }
            '^(--help|-h)$' { Write-Host 'UNINSTALL.cmd [--home PATH] [--purge-data] [--yes] [--plan]'; exit 0 }
            default { throw ('Unknown uninstall option: '+$Options[$I]) }
        }
    }
    . (Join-Path $PSScriptRoot 'uninstall_windows.ps1')
    $MarkerRecovery=$false; $RecoveryEvidence=$null
    $Root=[IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $Marker=Join-Path $Root '.zetalvx-install.json'
    $DefaultRoot=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CreatorStudioSDXL')).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $Marker) -and $Root -eq $DefaultRoot -and (Test-Path -LiteralPath $Root -PathType Container)) {
        # 1.0.14 full removal could delete its marker before getting stuck in runtime.
        # Recover only the standard root and only with a previous full-removal spec.
        Assert-NoLinkedAncestors $Root
        foreach ($Folder in @(Get-ChildItem -LiteralPath ([IO.Path]::GetTempPath()) -Filter 'zetalvx-uninstall-*' -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 100)) {
            try {
                $Evidence=Join-Path $Folder.FullName 'spec.json'; Assert-NoLinkedAncestors $Evidence
                $Previous=Get-Content -LiteralPath $Evidence -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($Previous.purge_data -is [bool] -and $Previous.purge_data -and $Previous.installation_id -match '^[a-f0-9]{32}$' -and $Previous.home -and [IO.Path]::GetFullPath([string]$Previous.home).TrimEnd([IO.Path]::DirectorySeparatorChar) -eq $Root) {
                    $Identity=@{schema=1;product='Zetalvx Creator Studio SDXL';id=[string]$Previous.installation_id;home=$Root}
                    $Install=[pscustomobject]@{home=$Root;id=$Identity.id;marker=$Identity}
                    $MarkerRecovery=$true; $RecoveryEvidence=$Evidence
                    break
                }
            } catch { } # No evidence is accepted unless all required checks succeed.
        }
    }
    if (-not $MarkerRecovery) { $Install=Read-Installation $Root }
    $Root=$Install.home
    if ($Plan) {
        @{home=$Root;installation_id=$Install.id;purge_data=$Purge;data_preserved=(-not $Purge);external_paths_deleted=$false;python_required=$false;marker_recovery=$MarkerRecovery;evidence=$RecoveryEvidence} | ConvertTo-Json
        exit 0
    }
    if (-not $Yes) {
        $Text='Rimuovere Zetalvx Image Lab e i runtime da:'+[Environment]::NewLine+$Root+[Environment]::NewLine+[Environment]::NewLine+
            'L''app e i suoi processi saranno arrestati. Termina o annulla prima eventuali lavori importanti. Puo riprendere una disinstallazione interrotta.'+[Environment]::NewLine+
            'Remove Zetalvx Image Lab and its runtimes? App processes and unfinished work will be stopped.'
        if (-not (Show-UninstallMessage $Text $true)) {exit 0}
        if (-not $Purge) {
            $Purge=Show-UninstallMessage ('Eliminare ANCHE modelli, immagini, progetti, preset e account in questa cartella?'+[Environment]::NewLine+
                'SI = elimina la cartella installata completa. NO = conserva i dati personali.'+[Environment]::NewLine+
                'Delete ALL personal data too? YES deletes the entire installed folder; NO keeps your data.') $true
        }
        if ($Purge -and -not (Show-UninstallMessage ('CONFERMA ELIMINAZIONE DEFINITIVA / CONFIRM PERMANENT DELETION'+[Environment]::NewLine+$Root+[Environment]::NewLine+
            'Tutti i dati contenuti nella cartella saranno eliminati. I collegamenti a modelli esterni non vengono seguiti.'+[Environment]::NewLine+
            'All data inside this folder will be deleted. External model links are not followed.') $true)) {exit 0}
    }
    if ($MarkerRecovery) {
        if (-not $Yes -and -not (Show-UninstallMessage ('La vecchia rimozione ha lasciato una cartella priva del file identificativo.'+[Environment]::NewLine+
            'Riprendere la rimozione di questa cartella usando il report precedente?'+[Environment]::NewLine+$Root+[Environment]::NewLine+$RecoveryEvidence+[Environment]::NewLine+
            'Resume the interrupted uninstall using its previous local report?') $true)) {exit 0}
        Assert-NoLinkedAncestors $Root
        # CreateNew refuses to overwrite an identity written by another operation.
        $Stream=[IO.File]::Open($Marker,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $Bytes=(New-Object Text.UTF8Encoding($false)).GetBytes(($Install.marker | ConvertTo-Json))
            $Stream.Write($Bytes,0,$Bytes.Length);$Stream.Flush()
        } finally {$Stream.Dispose()}
        Write-Host ('Identita recuperata dal report / Identity recovered from: '+$RecoveryEvidence)
    }
    $Report=Join-Path ([IO.Path]::GetTempPath()) ('zetalvx-uninstall-'+[Guid]::NewGuid().ToString('N'))
    if ($Report -eq $Root -or (Test-UnderRoot $Report $Root)) {throw 'TEMP must be outside the application folder.'}
    Assert-NoLinkedAncestors ([IO.Path]::GetDirectoryName($Report))
    [IO.Directory]::CreateDirectory($Report) | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall_windows.ps1') -Destination (Join-Path $Report 'cleanup.ps1')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall_tree.cs') -Destination (Join-Path $Report 'uninstall_tree.cs')
    $Spec=Join-Path $Report 'spec.json'
    Write-JsonAtomic $Spec @{schema='zetalvx.native-uninstall.v1';id=[Guid]::NewGuid().ToString('N');home=$Root;installation_id=$Install.id;purge_data=[bool]$Purge;gui=[bool]($Gui -or -not $Yes);recover_legacy=$true}
    $PowerShell=Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
    # A new process outside the installation owns the whole stop/delete/verify cycle.
    $QuotedScript='"'+(Join-Path $Report 'cleanup.ps1')+'"'
    $QuotedSpec='"'+$Spec+'"'
    $Child=Start-Process -FilePath $PowerShell -ArgumentList @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$QuotedScript,'-SpecPath',$QuotedSpec) -WorkingDirectory $Report -PassThru
    Write-Host ('Disinstallazione nella nuova finestra / Uninstall in new window. PID: '+$Child.Id)
    Write-Host ('Risultato finale / Final result: '+(Join-Path $Report 'result.json'))
    exit 0
} catch {
    Write-Host ('[ERROR] '+$_.Exception.Message)
    if ($Gui -and (Get-Command Show-UninstallMessage -ErrorAction SilentlyContinue)) {try {Show-UninstallMessage $_.Exception.Message} catch {}}
    exit 2
}
