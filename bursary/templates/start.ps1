Set-Location $PSScriptRoot
.\.venv\Scripts\Activate.ps1
if (-not $env:MYSQL_PASSWORD) {
    $env:MYSQL_PASSWORD = Read-Host "Enter your MySQL password"
}
Start-Job { Start-Sleep 5; Start-Process "http://127.0.0.1:8000/admin/" } | Out-Null
python manage.py runserver