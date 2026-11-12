[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$desktopExecutable = Join-Path $repositoryRoot 'native/windows/artifacts/revamp-ui-app/ApexBooks.Windows.exe'
if (-not (Test-Path -LiteralPath $desktopExecutable -PathType Leaf)) {
    throw 'The Windows review build is missing. See native/NATIVE_REVAMP_REVIEW.md for build and verification details.'
}

$previewOrigin = "http://127.0.0.1:$ApiPort"
try {
    $null = Invoke-RestMethod -Uri "$previewOrigin/api/ready" -TimeoutSec 5
} catch {
    throw 'Start the local demo first: .venv/Scripts/python.exe scripts/preview_local.py'
}

# Scope the local API override to this app process; preserve the caller's environment.
$launch = New-Object System.Diagnostics.ProcessStartInfo
$launch.FileName = $desktopExecutable
$launch.WorkingDirectory = Split-Path -Parent $desktopExecutable
$launch.UseShellExecute = $false
$launch.EnvironmentVariables['APEX_BOOKS_API_ORIGIN'] = $previewOrigin
$desktopProcess = [System.Diagnostics.Process]::Start($launch)
Write-Output "Opened the Windows demo (process $($desktopProcess.Id))."
Write-Output 'Synthetic demo login: demo@apexbooks.local / ApexDemo-2026!'
