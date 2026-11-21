param(
    [string] $EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string[]] $Scripts = @(
        'VerifySprint.py',
        'VerifySidewalk.py',
        'VerifyCitizens.py',
        'VerifyDayNightHud.py',
        'VerifyTrafficNetwork.py',
        'VerifyCalendar.py',
        'VerifyCitizenLod.py',
        'VerifyCrossing.py',
        'VerifyInteraction.py',
        'VerifyEconomy.py',
        'VerifyMap.py',
        'VerifyTasks.py',
        'VerifyPriority.py',
        'VerifyParking.py',
        'VerifySaveGame.py'
    )
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$project = Join-Path $repository 'unreal\DoemitzLivingCity\DoemitzLivingCity.uproject'
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$verifyDir = Join-Path (Split-Path -Parent $project) 'Content\Python\Verify'
$logDir = Join-Path (Split-Path -Parent $project) 'Saved\Logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$expectedMarkers = @{
    'VerifySprint.py'         = 'DOEMITZ_SPRINT_PIE_OK:'
    'VerifySidewalk.py'       = 'DOEMITZ_SIDEWALK_PIE_OK:'
    'VerifyCitizens.py'       = 'DOEMITZ_CITIZENS_PIE_OK:'
    'VerifyDayNightHud.py'    = 'DOEMITZ_DAYNIGHT_HUD_PIE_OK:'
    'VerifyTrafficNetwork.py' = 'DOEMITZ_TRAFFIC_NETWORK_PIE_OK:'
    'VerifyCalendar.py'       = 'DOEMITZ_CALENDAR_PIE_OK:'
    'VerifyCitizenLod.py'     = 'DOEMITZ_CITIZEN_LOD_PIE_OK:'
    'VerifyCrossing.py'       = 'DOEMITZ_CROSSING_PIE_OK:'
    'VerifyInteraction.py'    = 'DOEMITZ_INTERACTION_PIE_OK:'
    'VerifyEconomy.py'        = 'DOEMITZ_ECONOMY_PIE_OK:'
    'VerifyMap.py'            = 'DOEMITZ_MAP_PIE_OK:'
    'VerifyTasks.py'          = 'DOEMITZ_TASKS_PIE_OK:'
    'VerifyPriority.py'       = 'DOEMITZ_PRIORITY_PIE_OK:'
    'VerifyParking.py'        = 'DOEMITZ_PARKING_PIE_OK:'
    'VerifySaveGame.py'       = 'DOEMITZ_SAVEGAME_PIE_OK:'
}

$results = @()
foreach ($scriptName in $Scripts) {
    $scriptPath = Join-Path $verifyDir $scriptName
    if (!(Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        throw "Verification script not found: $scriptPath"
    }
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($scriptName)
    $logPath = Join-Path $logDir ("{0}.log" -f $stem)
    $argsList = @(
        ('"{0}"' -f $project)
        ('-ExecutePythonScript="{0}"' -f $scriptPath)
        '-nullrhi'
        '-unattended'
        '-nosplash'
        '-NoSound'
        '-NoLiveCoding'
        ('-abslog="{0}"' -f $logPath)
    )
    Write-Host "Running PIE check: $scriptName ..."
    $proc = Start-Process -FilePath $editor -ArgumentList $argsList -WindowStyle Hidden -PassThru -Wait
    if ($proc.ExitCode -ne 0) {
        Get-Content -LiteralPath $logPath -Tail 35 -ErrorAction SilentlyContinue
        throw "$scriptName exited with code $($proc.ExitCode). See $logPath"
    }
    $marker = $expectedMarkers[$scriptName]
    if ($marker) {
        $hit = Select-String -LiteralPath $logPath -SimpleMatch $marker | Select-Object -Last 1
        if (!$hit) {
            Get-Content -LiteralPath $logPath -Tail 35 -ErrorAction SilentlyContinue
            throw "$scriptName did not emit marker '$marker'. See $logPath"
        }
        $results += $hit.Line
        Write-Host $hit.Line
    }
}

Write-Host "DOEMITZ_VERIFY_ALL_OK: $($results.Count)/$($Scripts.Count) PIE checks passed."
