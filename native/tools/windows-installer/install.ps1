# Apex Books per-user installer. Copies the app to %LOCALAPPDATA%\Programs\Apex Books, adds Start menu and
# desktop shortcuts and an entry in Settings > Apps so it can be uninstalled. Company data is stored by the
# app itself and is not touched by installing, upgrading or uninstalling.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'win-x64'
$exeName = 'ApexBooks.Windows.exe'
if (-not (Test-Path -LiteralPath (Join-Path $source $exeName))) { throw "Extract the whole zip first, then run 'Install Apex Books' from the extracted folder." }
$target = Join-Path $env:LOCALAPPDATA 'Programs\Apex Books'
$running = Get-Process -Name 'ApexBooks.Windows' -ErrorAction SilentlyContinue
if ($running) {
    Write-Host 'Apex Books is open. Close it to continue the installation.' -ForegroundColor Yellow
    $running | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    Start-Sleep -Seconds 4
    if (Get-Process -Name 'ApexBooks.Windows' -ErrorAction SilentlyContinue) { throw 'Apex Books is still open. Close it and run the installer again.' }
}
Write-Host "Installing Apex Books to $target ..."
New-Item -ItemType Directory -Path $target -Force | Out-Null
robocopy $source $target /MIR /NFL /NDL /NJH /NJS /NP /R:2 /W:1 | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Copying files failed (robocopy exit code $LASTEXITCODE)." }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall.ps1') -Destination (Join-Path $target 'uninstall.ps1') -Force
$exe = Join-Path $target $exeName
$icon = Join-Path $target 'Assets\AppIcon.ico'
$version = (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
    $link = $shell.CreateShortcut((Join-Path $folder 'Apex Books.lnk'))
    $link.TargetPath = $exe; $link.WorkingDirectory = $target; $link.IconLocation = $icon; $link.Description = 'Apex Books accounting'
    $link.Save()
}
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ApexBooks'
New-Item -Path $key -Force | Out-Null
$size = [int]((Get-ChildItem -LiteralPath $target -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
$values = @{ DisplayName = 'Apex Books'; DisplayVersion = "$version"; Publisher = 'Apex Books'; DisplayIcon = $icon; InstallLocation = $target
    UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$target\uninstall.ps1`"" }
foreach ($name in $values.Keys) { New-ItemProperty -Path $key -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null }
foreach ($name in 'NoModify', 'NoRepair') { New-ItemProperty -Path $key -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
New-ItemProperty -Path $key -Name EstimatedSize -Value $size -PropertyType DWord -Force | Out-Null
Write-Host "Apex Books $version is installed. Opening it now." -ForegroundColor Green
Start-Process -FilePath $exe -WorkingDirectory $target
