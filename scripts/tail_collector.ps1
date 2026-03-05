param(
    [string]$EnvFile = "",
    [int]$Tail = 200
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")

$safeName = if ($EnvFile -and $EnvFile.Trim()) {
    ($EnvFile -replace "[^a-zA-Z0-9._-]", "_")
} else {
    "default"
}

$logFile = Join-Path (Join-Path $projectRoot "logs") "collector.$safeName.log"
if (-not (Test-Path $logFile)) {
    Write-Host "日志文件不存在: $logFile"
    exit 1
}

Get-Content -Path $logFile -Tail $Tail -Wait
