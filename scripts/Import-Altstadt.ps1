param(
    [string] $EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string] $PythonExe,
    [switch] $SkipHLOD
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
if (!$PythonExe) {
    $PythonExe = Join-Path $repository '.venv\Scripts\python.exe'
}
$project = Join-Path $repository 'unreal\DoemitzLivingCity\DoemitzLivingCity.uproject'
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$importScript = Join-Path (Split-Path -Parent $project) 'Content\Python\import_altstadt.py'
$log = Join-Path (Split-Path -Parent $project) 'Saved\Logs\AltstadtImport.log'
$hlodLog = Join-Path (Split-Path -Parent $project) 'Saved\Logs\AltstadtHLOD.log'

Push-Location -LiteralPath $repository
try {
    & $PythonExe -m tools.mesh_generator
    if ($LASTEXITCODE -ne 0) {
        throw 'Mesh generation failed.'
    }

    Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
    $editorArguments = @(
        ('"{0}"' -f $project)
        '-run=pythonscript'
        ('-script="{0}"' -f $importScript)
        '-nullrhi'
        '-unattended'
        '-nosplash'
        '-NoSound'
        '-NoLiveCoding'
        ('-abslog="{0}"' -f $log)
    )
    $process = Start-Process -FilePath $editor -ArgumentList $editorArguments -WindowStyle Hidden -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        Get-Content -LiteralPath $log -Tail 35 -ErrorAction SilentlyContinue
        throw "Unreal import exited with code $($process.ExitCode)."
    }
    $result = Select-String -LiteralPath $log -SimpleMatch 'DOEMITZ_IMPORT_OK:' | Select-Object -Last 1
    if (!$result) {
        throw "Unreal import has no completion marker. See $log"
    }
    $result.Line

    if (!$SkipHLOD) {
        Remove-Item -LiteralPath $hlodLog -Force -ErrorAction SilentlyContinue
        $hlodArguments = @(
            ('"{0}"' -f $project)
            '/Game/Maps/DoemitzAltstadt'
            '-run=WorldPartitionBuilderCommandlet'
            '-Builder=WorldPartitionHLODsBuilder'
            '-SetupHLODs'
            '-BuildHLODs'
            '-AllowCommandletRendering'
            '-unattended'
            '-nosplash'
            '-NoSound'
            '-NoLiveCoding'
            ('-abslog="{0}"' -f $hlodLog)
        )
        Write-Host 'Building World Partition HLODs for /Game/Maps/DoemitzAltstadt ...'
        $hlodProc = Start-Process -FilePath $editor -ArgumentList $hlodArguments -WindowStyle Hidden -PassThru -Wait
        if ($hlodProc.ExitCode -ne 0) {
            Get-Content -LiteralPath $hlodLog -Tail 40 -ErrorAction SilentlyContinue
            throw "World Partition HLOD build exited with code $($hlodProc.ExitCode). See $hlodLog"
        }
        $hlodSummary = Select-String -LiteralPath $hlodLog -SimpleMatch 'World contains' | Select-Object -Last 1
        if ($hlodSummary) {
            $hlodSummary.Line
        }
    }
}
finally {
    Pop-Location
}
