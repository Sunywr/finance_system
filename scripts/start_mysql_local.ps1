param(
    [int]$Port = 3307,
    [string]$DataDir = "",
    [string]$Mysqld = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $DataDir) { $DataDir = Join-Path $root ".mysql-data" }
if (-not $Mysqld) {
    $candidate = "D:\Software\Env\mysql8\bin\mysqld.exe"
    if (Test-Path $candidate) { $Mysqld = $candidate } else { $Mysqld = "mysqld.exe" }
}
$mysql = Join-Path (Split-Path -Parent $Mysqld) "mysql.exe"
$mysqladmin = Join-Path (Split-Path -Parent $Mysqld) "mysqladmin.exe"
$ini = Join-Path $root ".mysql-local.ini"

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "MySQL 已在 127.0.0.1:$Port 运行" -ForegroundColor Green
} else {
    $iniContent = @"
[mysqld]
basedir=$(Split-Path -Parent (Split-Path -Parent $Mysqld))
datadir=$($DataDir -replace '\\','/')
innodb_undo_directory=$($DataDir -replace '\\','/')
port=$Port
bind-address=127.0.0.1
lower_case_table_names=1
mysqlx=0
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci
log-error=$($DataDir -replace '\\','/')/error.log
"@
    Set-Content -Path $ini -Value $iniContent -Encoding ASCII
    if (-not (Test-Path (Join-Path $DataDir "mysql"))) {
        Write-Host "初始化独立 MySQL 数据目录: $DataDir" -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
        & $Mysqld "--defaults-file=$ini" --initialize-insecure --console 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "MySQL 初始化失败" }
    }
    # Workaround for the portable MySQL 8.4.7 build on this machine: it may try to
    # re-create undo tablespaces on restart and abort because the files exist.
    # Deleting them while the server is stopped lets InnoDB recreate them cleanly.
    foreach ($undoFile in @("undo_001", "undo_002", "undo_1_trunc.log")) {
        $undoPath = Join-Path $DataDir $undoFile
        if (Test-Path $undoPath) {
            Remove-Item $undoPath -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "启动独立 MySQL 127.0.0.1:$Port" -ForegroundColor Cyan
    Start-Process -FilePath $Mysqld -ArgumentList @("--defaults-file=$ini", "--console") `
        -WorkingDirectory $DataDir -WindowStyle Hidden | Out-Null
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
            $ready = $true
            break
        }
    }
    if (-not $ready) { throw "MySQL 未在预期时间内启动，请查看 $DataDir\error.log" }
    Write-Host "MySQL 已启动" -ForegroundColor Green
}

# Ensure the application database/user exist, using the password in backend/.env.
$envFile = Join-Path $root "backend\.env"
$dbPassword = ""
if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^DB_PASSWORD=" } | Select-Object -First 1
    if ($line) { $dbPassword = $line.Substring("DB_PASSWORD=".Length) }
}
if (-not $dbPassword) {
    $chars = (48..57) + (65..90) + (97..122)
    $dbPassword = -join (1..28 | ForEach-Object { [char]($chars | Get-Random) })
    Add-Content -Path $envFile -Value "DB_PASSWORD=$dbPassword" -Encoding UTF8
}
$escaped = $dbPassword.Replace("'", "''")
$sql = @"
CREATE DATABASE IF NOT EXISTS finance CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'finance_app'@'localhost' IDENTIFIED BY '$escaped';
CREATE USER IF NOT EXISTS 'finance_app'@'127.0.0.1' IDENTIFIED BY '$escaped';
ALTER USER 'finance_app'@'localhost' IDENTIFIED BY '$escaped';
ALTER USER 'finance_app'@'127.0.0.1' IDENTIFIED BY '$escaped';
GRANT ALL PRIVILEGES ON finance.* TO 'finance_app'@'localhost';
GRANT ALL PRIVILEGES ON finance.* TO 'finance_app'@'127.0.0.1';
GRANT ALL PRIVILEGES ON test_finance.* TO 'finance_app'@'localhost';
GRANT ALL PRIVILEGES ON test_finance.* TO 'finance_app'@'127.0.0.1';
FLUSH PRIVILEGES;
"@
& $mysql -h 127.0.0.1 -P $Port -u root -e $sql
if ($LASTEXITCODE -ne 0) { throw "创建 finance 数据库/用户失败" }
Write-Host "数据库 finance 与账号 finance_app 已就绪（端口 $Port）" -ForegroundColor Green
