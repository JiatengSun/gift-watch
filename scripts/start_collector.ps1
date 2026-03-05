param(
    [string]$EnvFile = "",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $projectRoot

$safeName = if ($EnvFile -and $EnvFile.Trim()) {
    ($EnvFile -replace "[^a-zA-Z0-9._-]", "_")
} else {
    "default"
}

$logDir = Join-Path $projectRoot "logs"
$runDir = Join-Path $projectRoot "run"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
New-Item -ItemType Directory -Path $runDir -Force | Out-Null

$pidFile = Join-Path $runDir "collector.$safeName.pid"
$logFile = Join-Path $logDir "collector.$safeName.log"

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid) {
        try {
            $proc = Get-Process -Id ([int]$existingPid) -ErrorAction Stop
            Write-Host "collector 已在运行: PID=$($proc.Id) EnvFile='$EnvFile' Log=$logFile"
            exit 0
        } catch {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
    }
}

$args = @("-u", "collector_bot.py")
if ($EnvFile -and $EnvFile.Trim()) {
    $args += @("--env-file", $EnvFile)
}

$proc = Start-Process -FilePath $PythonExe -ArgumentList $args -WorkingDirectory $projectRoot -RedirectStandardOutput $logFile -RedirectStandardError $logFile -PassThru
Set-Content -Path $pidFile -Value $proc.Id -NoNewline

Write-Host "collector 已启动: PID=$($proc.Id)"
Write-Host "EnvFile: $EnvFile"
Write-Host "Log: $logFile"
Write-Host "PID file: $pidFile"
