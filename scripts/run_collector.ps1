param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $projectRoot

$args = @("collector_bot.py")
if ($EnvFile -and $EnvFile.Trim()) {
    $args += @("--env-file", $EnvFile)
}

python @args
