# Removes the Apex Books program files, shortcuts and Apps entry. Company data stays in your account and on the server.
$ErrorActionPreference = 'Continue'
Get-Process -Name 'ApexBooks.Windows' -ErrorAction SilentlyContinue | Stop-Process -Force
foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
    Remove-Item -LiteralPath (Join-Path $folder 'Apex Books.lnk') -Force -ErrorAction SilentlyContinue
}
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ApexBooks' -Recurse -Force -ErrorAction SilentlyContinue
$target = Join-Path $env:LOCALAPPDATA 'Programs\Apex Books'
Set-Location $env:TEMP
Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'Apex Books has been uninstalled.'
