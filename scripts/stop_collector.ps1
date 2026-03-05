param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")

$safeName = if ($EnvFile -and $EnvFile.Trim()) {
    ($EnvFile -replace "[^a-zA-Z0-9._-]", "_")
} else {
    "default"
}

$pidFile = Join-Path (Join-Path $projectRoot "run") "collector.$safeName.pid"
if (-not (Test-Path $pidFile)) {
    Write-Host "未找到 PID 文件: $pidFile"
    exit 0
}

$pidText = (Get-Content $pidFile -Raw).Trim()
if (-not $pidText) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "PID 文件为空，已清理: $pidFile"
    exit 0
}

$pid = [int]$pidText
try {
    Stop-Process -Id $pid -Force -ErrorAction Stop
    Write-Host "已停止 collector: PID=$pid EnvFile='$EnvFile'"
} catch {
    Write-Host "进程可能已退出: PID=$pid"
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
