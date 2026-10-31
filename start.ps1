Set-Location $PSScriptRoot
.\.venv\Scripts\Activate.ps1
if (-not $env:MYSQL_PASSWORD) {
    $env:MYSQL_PASSWORD = Read-Host "Enter your MySQL password"
}
Start-Job { Start-Sleep 5; Start-Process "http://127.0.0.1:8000/admin/" } | Out-Null
python manage.py runserver
# BursaryNexa start script. It works from any folder.
$project = "C:\Users\Admin\Desktop\Desktop Folders\Documents\zetech docs\bursary-system\bursury-system"
Set-Location $project

# 1. Stop any old servers still running
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. Start MySQL if it is stopped
$mysql = Get-Service -Name "MySQL*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($mysql -and $mysql.Status -ne "Running") {
    Write-Host "Starting $($mysql.Name)..."
    try { Start-Service $mysql.Name } catch { Write-Host "Could not start MySQL. Start it in Windows Services, or run this script as Administrator." }
}

# 3. Run the site with the project's own Python
& "$project\.venv\Scripts\python.exe" manage.py runserver