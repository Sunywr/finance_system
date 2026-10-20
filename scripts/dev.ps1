param(
    [switch]$Scheduler,
    [switch]$NoFrontend
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host "启动 Django API: http://127.0.0.1:8000" -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$backend'; python manage.py runserver 127.0.0.1:8000"
)

if ($Scheduler) {
    Write-Host "启动定时任务进程" -ForegroundColor Cyan
    Start-Process pwsh -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$backend'; python manage.py run_scheduler"
    )
}

if (-not $NoFrontend) {
    Write-Host "启动前端: http://127.0.0.1:5173" -ForegroundColor Cyan
    Start-Process pwsh -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$frontend'; pnpm dev"
    )
}

Write-Host ""
Write-Host "若首次运行，请先执行 scripts/init_db.ps1 配置 MySQL。" -ForegroundColor Yellow
