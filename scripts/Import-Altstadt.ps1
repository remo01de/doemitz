param(
    [string] $EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string] $PythonExe
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
}
finally {
    Pop-Location
}
