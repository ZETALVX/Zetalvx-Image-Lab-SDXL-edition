#Requires -Version 5.1
# Regression for the 1.0.16 File.Replace fix. Only private TEMP JSON fixtures.
# Does NOT invoke the uninstaller, stop processes or touch any installed app.
param([string]$SourceRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
. (Join-Path $SourceRoot 'scripts/uninstall_windows.ps1')
$Fixture = Join-Path ([IO.Path]::GetTempPath()) ('zetalvx-json-116-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($Fixture) | Out-Null
$Checks = @()
function Assert-Test([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
try {
    # Spaces/brackets exercise literal filesystem paths, not provider patterns.
    $Folder = Join-Path $Fixture 'atomic test [116]'
    [IO.Directory]::CreateDirectory($Folder) | Out-Null
    $JsonPath = Join-Path $Folder 'state.json'
    $UnicodeText = 'test-' + [char]0x00E8 + '-' + [char]0x6D4B
    Write-JsonAtomic $JsonPath @{seq=1; text=$UnicodeText}
    $Read = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($Read.seq -eq 1 -and $Read.text -eq $UnicodeText) 'Initial JSON creation failed.'
    $Checks += 'create_json_literal_path_utf8'

    # The OLD implementation creates a file but fails on its first overwrite.
    for ($I=2; $I -le 30; $I++) {
        Write-JsonAtomic $JsonPath @{seq=$I; text=$UnicodeText}
        $Read = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Test ($Read.seq -eq $I -and $Read.text -eq $UnicodeText) ('Overwrite failed: ' + $I)
    }
    Assert-Test (@(Get-ChildItem -LiteralPath $Folder -Force).Count -eq 1) 'Overwrite left temporary/backup files.'
    $Checks += 'overwrite_existing_json_29_times_no_residue'

    $Pending = Join-Path $Folder 'uninstall-pending.json'
    Write-JsonAtomic $Pending @{id='old'; status='starting'}
    Write-JsonAtomic $Pending @{id='new'; status='cleanup'}
    $Read = Get-Content -LiteralPath $Pending -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($Read.id -eq 'new' -and $Read.status -eq 'cleanup') 'Pending JSON replacement failed.'
    $Checks += 'replace_preexisting_pending_json'

    $Report = Join-Path $Fixture 'report'
    [IO.Directory]::CreateDirectory($Report) | Out-Null
    $script:ReportFolder = $Report
    $script:CleanupRoot = Join-Path $Fixture 'not-an-installation'
    Write-CleanupProgress 'validating' 'Cartella installata / Installed folder: fixture only'
    Write-CleanupProgress 'validating' 'Rimozione completa / Delete personal data: True'
    $Read = Get-Content -LiteralPath (Join-Path $Report 'progress.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($Read.phase -eq 'validating' -and $Read.detail -match 'True$') 'Second progress update failed.'
    Assert-Test (@(Get-Content -LiteralPath (Join-Path $Report 'cleanup.log')).Count -eq 2) 'Progress log is incomplete.'
    $Checks += 'second_progress_update_user_failure_point'

    # Exercise the reporting path that formerly raised the SAME exception again.
    Write-CleanupProgress 'failed' 'ERRORE / ERROR: simulated failure, no uninstall performed'
    Write-JsonAtomic (Join-Path $Report 'result.json') @{ok=$false; error='simulated'}
    Write-JsonAtomic (Join-Path $Report 'progress.json') @{status='failed'; phase='failed'}
    $Read = Get-Content -LiteralPath (Join-Path $Report 'progress.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $Result = Get-Content -LiteralPath (Join-Path $Report 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($Read.status -eq 'failed' -and $Result.ok -eq $false) 'Error-result reporting failed.'
    $Checks += 'error_reporting_without_second_replace_exception'

    Write-JsonAtomic (Join-Path $Report 'result.json') @{ok=$true; test_only=$true}
    Write-JsonAtomic (Join-Path $Report 'progress.json') @{status='completed'; phase='completed'}
    $Read = Get-Content -LiteralPath (Join-Path $Report 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Test ($Read.ok -eq $true -and $Read.test_only -eq $true) 'Final result replacement failed.'
    Assert-Test (@(Get-ChildItem -LiteralPath $Report -Force).Count -eq 3) 'Reporting left temporary/backup files.'
    $Checks += 'final_result_overwrite_no_residue'

    # Negative control: demonstrate the old argument conversion on Windows PS 5.1.
    $OldSource = Join-Path $Fixture 'old-source.json'
    $OldDest = Join-Path $Fixture 'old-dest.json'
    [IO.File]::WriteAllText($OldSource, '{"seq":2}')
    [IO.File]::WriteAllText($OldDest, '{"seq":1}')
    $LegacyFailed = $false
    $LegacyError = $null
    try { [IO.File]::Replace($OldSource, $OldDest, $null) }
    catch { $LegacyFailed = $true; $LegacyError = $_.Exception.Message }
    if ($PSVersionTable.PSVersion.Major -eq 5) {
        Assert-Test $LegacyFailed 'Expected legacy null-to-empty-string failure was not reproduced on PS 5.'
    }
    $Checks += 'legacy_negative_control_recorded'
    @{
        ok=$true; checks=$Checks; count=$Checks.Count;
        powershell=$PSVersionTable.PSVersion.ToString(); edition=$PSVersionTable.PSEdition;
        native_windows=($env:OS -eq 'Windows_NT'); full_uninstall_tested=$false;
        legacy_bug_reproduced=$LegacyFailed; legacy_error=$LegacyError
    } | ConvertTo-Json -Depth 5 | Write-Host
    exit 0
} catch {
    Write-Host ('[JSON REGRESSION FAILED] ' + $_.Exception.Message)
    Write-Host $_.ScriptStackTrace
    exit 1
} finally {
    $script:ReportFolder = $null
    # Only this unique test-owned folder is removed; no real app path is accepted.
    if ([IO.Directory]::Exists($Fixture)) { [IO.Directory]::Delete($Fixture, $true) }
}
