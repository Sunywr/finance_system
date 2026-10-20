param([int]$Port = 3307)

$mysqladmin = "D:\Software\Env\mysql8\bin\mysqladmin.exe"
if (-not (Test-Path $mysqladmin)) { $mysqladmin = "mysqladmin.exe" }
& $mysqladmin -h 127.0.0.1 -P $Port -u root shutdown
if ($LASTEXITCODE -eq 0) {
    Write-Host "独立 MySQL 已停止（端口 $Port）" -ForegroundColor Green
} else {
    Write-Host "停止失败，请确认 MySQL 是否在该端口运行" -ForegroundColor Yellow
}
