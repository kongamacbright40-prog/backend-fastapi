# Resets the password of the PostgreSQL "postgres" user when it is forgotten.
#
# Run in PowerShell **as Administrator** (right-click PowerShell > Run as
# administrator), from the smart-classroom-api folder:
#
#   powershell -ExecutionPolicy Bypass -File scripts\reset_postgres_password.ps1
#
# What it does: temporarily lets local connections in without a password
# (pg_hba.conf "trust" for 127.0.0.1 / ::1 only), sets the new password, then
# puts the original pg_hba.conf back and restarts PostgreSQL. A backup of
# pg_hba.conf is kept next to it.

param(
    [string]$ServiceName = "postgresql-x64-18",
    [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
    [string]$DataDir = "C:\Program Files\PostgreSQL\18\data",
    [string]$User = "postgres",
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Please run this in PowerShell opened with 'Run as administrator'." -ForegroundColor Red
    exit 1
}

$hba = Join-Path $DataDir "pg_hba.conf"
$backup = "$hba.before-password-reset"
if (-not (Test-Path $hba)) { throw "pg_hba.conf not found at $hba" }

$newPassword = Read-Host "New password for PostgreSQL user '$User' (visible as you type)"
if ([string]::IsNullOrWhiteSpace($newPassword)) { throw "The password cannot be empty." }
$confirm = Read-Host "Type it again"
if ($newPassword -ne $confirm) { throw "The two passwords are different. Nothing was changed." }

Copy-Item $hba $backup -Force
try {
    # Local TCP connections only; everything else keeps its normal rule.
    $lines = Get-Content $hba
    $trusted = $lines | ForEach-Object {
        if ($_ -match '^\s*host\s+all\s+all\s+(127\.0\.0\.1/32|::1/128)\s+\S+') {
            $_ -replace '\S+\s*$', 'trust'
        } else { $_ }
    }
    Set-Content -Path $hba -Value $trusted -Encoding ascii
    Write-Host "Restarting PostgreSQL (temporary local access)..."
    Restart-Service $ServiceName
    Start-Sleep -Seconds 3

    # Doubled single quotes are how SQL escapes a quote inside a string.
    $sqlPassword = $newPassword.Replace("'", "''")
    & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U $User -d postgres -v ON_ERROR_STOP=1 `
        -c "ALTER USER `"$User`" WITH PASSWORD '$sqlPassword';"
    if ($LASTEXITCODE -ne 0) { throw "Could not set the password (psql exit code $LASTEXITCODE)." }
    Write-Host "Password changed." -ForegroundColor Green
}
finally {
    Copy-Item $backup $hba -Force
    Write-Host "Restoring the normal password check and restarting PostgreSQL..."
    Restart-Service $ServiceName
}

Write-Host ""
Write-Host "Done. Use the new password in pgAdmin and for:"
Write-Host "  python scripts\postgres_setup.py --show-password"
