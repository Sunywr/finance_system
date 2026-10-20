param(
    [string]$RootUser = "root",
    [string]$MysqlExe = "",
    [string]$Database = "finance",
    [string]$AppUser = "finance_app",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $root "backend\.env" }
if (-not $MysqlExe) {
    $candidate = "D:\Software\Env\mysql8\bin\mysql.exe"
    if (Test-Path $candidate) { $MysqlExe = $candidate } else { $MysqlExe = "mysql.exe" }
}

if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $root "backend\.env.example") $EnvFile
}

$secure = Read-Host "请输入本机 MySQL root 密码（不会写入仓库）" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $rootPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$chars = (48..57) + (65..90) + (97..122)
$appPassword = -join (1..28 | ForEach-Object { [char]($chars | Get-Random) })

function New-OptionFile {
    param([string]$Password)
    $path = Join-Path $env:TEMP ("mysql-init-" + [guid]::NewGuid().ToString("N") + ".cnf")
    $escaped = $Password.Replace("\", "\\").Replace('"', '\"')
    $content = "[client]`r`nuser=$RootUser`r`npassword=`"$escaped`"`r`nhost=127.0.0.1`r`nport=3306`r`n"
    Set-Content -Path $path -Value $content -Encoding ASCII
    return $path
}

function Invoke-Sql {
    param([string]$Sql, [string]$OptionFile)
    $output = & $MysqlExe "--defaults-extra-file=$OptionFile" -e $Sql 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL 执行失败: $output"
    }
    return $output
}

$optionFile = New-OptionFile -Password $rootPassword
try {
    $escapedApp = $appPassword.Replace("'", "''")
    $sql = @"
CREATE DATABASE IF NOT EXISTS ``$Database`` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '$AppUser'@'localhost' IDENTIFIED BY '$escapedApp';
CREATE USER IF NOT EXISTS '$AppUser'@'127.0.0.1' IDENTIFIED BY '$escapedApp';
ALTER USER '$AppUser'@'localhost' IDENTIFIED BY '$escapedApp';
ALTER USER '$AppUser'@'127.0.0.1' IDENTIFIED BY '$escapedApp';
GRANT ALL PRIVILEGES ON ``$Database``.* TO '$AppUser'@'localhost';
GRANT ALL PRIVILEGES ON ``$Database``.* TO '$AppUser'@'127.0.0.1';
GRANT ALL PRIVILEGES ON ``test_$Database``.* TO '$AppUser'@'localhost';
GRANT ALL PRIVILEGES ON ``test_$Database``.* TO '$AppUser'@'127.0.0.1';
FLUSH PRIVILEGES;
"@
    Invoke-Sql -Sql $sql -OptionFile $optionFile | Out-Null
} finally {
    Remove-Item $optionFile -Force -ErrorAction SilentlyContinue
    Remove-Variable rootPassword -ErrorAction SilentlyContinue
}

function Set-EnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = Get-Content $Path
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($Key))=") {
            "$Key=$Value"
            $found = $true
        } else {
            $line
        }
    }
    if (-not $found) { $updated += "$Key=$Value" }
    Set-Content -Path $Path -Value $updated -Encoding UTF8
}

Set-EnvValue -Path $EnvFile -Key "DB_ENGINE" -Value "mysql"
Set-EnvValue -Path $EnvFile -Key "DB_NAME" -Value $Database
Set-EnvValue -Path $EnvFile -Key "DB_USER" -Value $AppUser
Set-EnvValue -Path $EnvFile -Key "DB_PASSWORD" -Value $appPassword
Set-EnvValue -Path $EnvFile -Key "DB_HOST" -Value "127.0.0.1"
Set-EnvValue -Path $EnvFile -Key "DB_PORT" -Value "3306"
Set-EnvValue -Path $EnvFile -Key "DB_TEST_NAME" -Value "test_$Database"

Write-Host ""
Write-Host "数据库初始化完成：" -ForegroundColor Green
Write-Host "  数据库: $Database"
Write-Host "  用户:   $AppUser"
Write-Host "  密码已写入: $EnvFile（该文件已被 .gitignore 忽略）"
Write-Host ""
Write-Host "下一步：" -ForegroundColor Cyan
Write-Host "  cd backend"
Write-Host "  python manage.py migrate"
Write-Host "  python manage.py seed_system_data"
Write-Host "  python manage.py seed_demo     # 可选演示数据"
