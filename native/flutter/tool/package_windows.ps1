# Builds the Flutter Windows app for production and packages it with the per-user installer.
#   powershell -NoProfile -ExecutionPolicy Bypass -File native\flutter\tool\package_windows.ps1
# Output: deliverables\Apex-Books-Windows-<version>-win-x64.zip  (extract, then run "Install Apex Books").
param(
    [string]$ApiOrigin = 'https://api.apexbooks.in',
    [string]$Flutter = 'C:\src\flutter\bin\flutter.bat'
)
$ErrorActionPreference = 'Stop'
$app = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repository = (Resolve-Path (Join-Path $app '..\..')).Path
if ($ApiOrigin -notmatch '^https://[A-Za-z0-9.-]+(:\d+)?$') { throw 'Use an https API origin such as https://api.apexbooks.in' }
Push-Location $app
try {
    & $Flutter build windows --release "--dart-define=APEX_API_ORIGIN=$ApiOrigin"
    if ($LASTEXITCODE -ne 0) { throw 'flutter build windows failed' }
} finally { Pop-Location }
$release = Join-Path $app 'build\windows\x64\runner\Release'
if (-not (Test-Path -LiteralPath (Join-Path $release 'ApexBooks.exe'))) { throw 'The build did not produce ApexBooks.exe' }

$staging = Join-Path $env:TEMP ('apexbooks-package-' + [Guid]::NewGuid().ToString('N'))
$appDir = Join-Path $staging 'app'
New-Item -ItemType Directory -Path $appDir -Force | Out-Null
Copy-Item -Path (Join-Path $release '*') -Destination $appDir -Recurse
# Flutter apps need the Microsoft C++ runtime; ship it next to the exe so PCs without it still run the app.
$redist = Get-ChildItem 'C:\Program Files*\Microsoft Visual Studio\*\*\VC\Redist\MSVC\*\x64\Microsoft.VC14*.CRT' -Directory -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $redist) { throw 'Visual C++ redistributable files were not found under Visual Studio' }
foreach ($dll in 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll') { Copy-Item -LiteralPath (Join-Path $redist.FullName $dll) -Destination $appDir }
$private = @(Get-ChildItem -LiteralPath $appDir -Recurse -File | Where-Object { $_.Name -match '^(\.env|signing\.)' -or $_.Extension -in '.jks', '.keystore', '.db', '.sqlite', '.pdb' })
if ($private.Count) { throw 'The package contains private or debug files; packaging stopped.' }
Copy-Item -Path (Join-Path $PSScriptRoot 'windows-installer\*') -Destination $staging

$version = ((Get-Item -LiteralPath (Join-Path $appDir 'ApexBooks.exe')).VersionInfo.ProductVersion -split '\+')[0]
$deliverables = Join-Path $repository 'deliverables'
New-Item -ItemType Directory -Path $deliverables -Force | Out-Null
$archive = Join-Path $deliverables "Apex-Books-Windows-$version-win-x64.zip"
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $archive -CompressionLevel Optimal
Remove-Item -LiteralPath $staging -Recurse -Force
[pscustomobject]@{
    Path = $archive
    Version = $version
    ApiOrigin = $ApiOrigin
    Bytes = (Get-Item -LiteralPath $archive).Length
    Sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
}
