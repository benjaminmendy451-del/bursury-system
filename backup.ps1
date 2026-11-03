# BursaryNexa database backup.  Run from the project folder:   .\backup.ps1
# Saves a dated .sql file in the "backups" folder (which Git ignores, because it holds student data).

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Read the MySQL settings from .env
$envValues = @{}
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $envValues[$matches[1]] = $matches[2].Trim() }
    }
}
$db   = if ($envValues["MYSQL_DB"])   { $envValues["MYSQL_DB"] }   else { "bursary" }
$user = if ($envValues["MYSQL_USER"]) { $envValues["MYSQL_USER"] } else { "root" }
$pass = $envValues["MYSQL_PASSWORD"]
$hostName = if ($envValues["MYSQL_HOST"]) { $envValues["MYSQL_HOST"] } else { "127.0.0.1" }
$port = if ($envValues["MYSQL_PORT"]) { $envValues["MYSQL_PORT"] } else { "3306" }

# Find mysqldump
$dump = (Get-Command mysqldump -ErrorAction SilentlyContinue).Source
if (-not $dump) {
    $found = Get-ChildItem "C:\Program Files\MySQL" -Recurse -Filter mysqldump.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $dump = $found.FullName }
}
if (-not $dump) { Write-Host "Could not find mysqldump.exe. Is MySQL installed?" -ForegroundColor Red; exit 1 }

New-Item -ItemType Directory -Force -Path "backups" | Out-Null
$file = "backups\$db-" + (Get-Date -Format "yyyy-MM-dd_HH-mm") + ".sql"

if ($pass) { $env:MYSQL_PWD = $pass } else {
    $secure = Read-Host "MySQL password for $user" -AsSecureString
    $env:MYSQL_PWD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
try {
    & $dump --host=$hostName --port=$port --user=$user --single-transaction --routines --result-file=$file $db
    if ($LASTEXITCODE -ne 0) { throw "mysqldump failed" }
    Write-Host "Backup saved to $file" -ForegroundColor Green
} finally {
    Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
}
