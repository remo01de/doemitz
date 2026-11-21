param(
    [string] $EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string] $ArchiveDirectory
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$projectDirectory = Join-Path $repository 'unreal\DoemitzLivingCity'
$project = Join-Path $projectDirectory 'DoemitzLivingCity.uproject'
if (!$ArchiveDirectory) {
    $ArchiveDirectory = Join-Path $projectDirectory 'Saved\Builds\Win64Development'
}
$archive = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ArchiveDirectory)
$automationTool = Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat'

$buildArguments = @(
    'BuildCookRun'
    "-project=$project"
    '-platform=Win64'
    '-clientconfig=Development'
    '-map=/Game/Maps/DoemitzAltstadt'
    '-build'
    '-cook'
    '-stage'
    '-pak'
    '-iostore'
    '-prereqs'
    '-nodebuginfo'
    '-archive'
    "-archivedirectory=$archive"
    '-nop4'
    '-unattended'
    '-utf8output'
)

& $automationTool @buildArguments
if ($LASTEXITCODE -ne 0) {
    throw "Unreal Automation Tool exited with code $($LASTEXITCODE)."
}

$executable = Join-Path $archive 'DoemitzLivingCity.exe'
if (!(Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "The packaged executable was not found at $executable."
}

Write-Output $executable
