param(
    [Parameter(Mandatory)][string]$PublishDirectory,
    [ValidateSet('Debug','Release')][string]$Configuration = 'Release'
)
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$output = (Resolve-Path -LiteralPath $PublishDirectory).Path
if ((Split-Path -Leaf $output) -ne 'win-x64') { throw 'Publish into a win-x64 directory so the portable archive has a consistent layout.' }
foreach ($required in @('ApexBooks.Windows.exe','ApexBooks.Windows.pri','App.xbf','MainPage.xbf','MainWindow.xbf','Assets\AppIcon.ico')) {
    if (-not (Test-Path -LiteralPath (Join-Path $output $required) -PathType Leaf)) { throw "The Windows package is missing $required" }
}
$files = @(Get-ChildItem -LiteralPath $output -File -Recurse)
$privateFiles = @($files | Where-Object { $_.Name -match '^(\.env($|\.)|signing\.)' -or $_.Extension -in @('.vyb','.apexbackup','.jks','.keystore','.dpapi','.db','.sqlite','.sqlite3') })
if ($privateFiles.Count) { throw 'The publish directory contains private data or signing material. Packaging was stopped.' }
$nestedBuildFiles = @($files | Where-Object { $_.FullName.Substring($output.Length) -match '\\(artifacts|bin|obj)\\' })
if ($nestedBuildFiles.Count) { throw 'The publish directory contains nested build outputs. Publish into a fresh directory before packaging.' }
$deliverables = Join-Path $repository 'deliverables'
New-Item -ItemType Directory -Path $deliverables -Force | Out-Null
$projectMetadata = [xml](Get-Content -LiteralPath (Join-Path $repository 'native\windows\ApexBooks.Windows.csproj') -Raw)
$releaseVersion = @($projectMetadata.Project.PropertyGroup.Version | Where-Object { $_ })[0]
$archive = Join-Path $deliverables "Apex-Books-Windows-$releaseVersion-$Configuration-win-x64.zip"
Compress-Archive -LiteralPath $output -DestinationPath $archive -Force -CompressionLevel Optimal
[pscustomobject]@{
    Path = $archive
    Hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    RuntimeFiles = $files.Count
    RuntimeBytes = ($files | Measure-Object Length -Sum).Sum
    PrivateFiles = $privateFiles.Count
    NestedBuildFiles = $nestedBuildFiles.Count
}
