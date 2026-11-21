param(
    [string] $Executable,
    [string] $Profile = 'Baseline',
    [int] $DurationSeconds = 90,
    [int] $WarmupSeconds = 3,
    [int] $ResX = 1920,
    [int] $ResY = 1080,
    [string] $OutputJson
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
if (!$Executable) {
    $Executable = Join-Path $repository 'unreal\DoemitzLivingCity\Saved\Builds\Win64Development\DoemitzLivingCity.exe'
}
if (!(Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Packaged executable not found at $Executable"
}

$benchDir = Join-Path $repository 'unreal\DoemitzLivingCity\Saved\Benchmarks'
New-Item -ItemType Directory -Path $benchDir -Force | Out-Null
if (!$OutputJson) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmss')
    $OutputJson = Join-Path $benchDir ("benchmark_{0}_{1}.json" -f $Profile, $stamp)
} else {
    $OutputJson = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputJson)
}

$argsList = @(
    '-DoemitzBenchmark'
    "-DoemitzProfile=$Profile"
    "-DoemitzBenchmarkDuration=$DurationSeconds"
    "-DoemitzBenchmarkWarmup=$WarmupSeconds"
    "-DoemitzBenchmarkOut=$OutputJson"
    "-ResX=$ResX"
    "-ResY=$ResY"
    '-Windowed'
    '-NoSound'
    '-unattended'
)

Write-Host "Running benchmark: profile=$Profile ${ResX}x${ResY} duration=${DurationSeconds}s -> $OutputJson"
$proc = Start-Process -FilePath $Executable -ArgumentList $argsList -PassThru -Wait
if ($proc.ExitCode -ne 0) {
    throw "Benchmark process exited with code $($proc.ExitCode)."
}
if (!(Test-Path -LiteralPath $OutputJson -PathType Leaf)) {
    throw "Benchmark JSON was not written to $OutputJson"
}

Get-Content -LiteralPath $OutputJson -Raw
