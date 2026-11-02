param([Parameter(Mandatory=$true)][string]$PublishDirectory,[Parameter(Mandatory=$true)][string]$ApiOrigin)
# Legacy filename; local synthetic service acceptance only, not a UI test.
$ErrorActionPreference='Stop'
$uri=[Uri]$ApiOrigin
if($uri.Scheme -ne 'http' -or $uri.Host -notin @('127.0.0.1','localhost','::1') -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/'){throw 'Only an explicit isolated loopback HTTP API is permitted.'}
$priorOrigin=$env:APEX_NATIVE_TEST_ORIGIN
$repository=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$publish=(Resolve-Path -LiteralPath $PublishDirectory).Path
if(-not(Test-Path -LiteralPath (Join-Path $publish 'ApexBooks.Windows.dll'))){throw 'The published Windows client is missing.'}
$fixture=Join-Path $repository 'tmp\native-refresh\native-logo-alpha-qa.png'
if(-not(Test-Path -LiteralPath $fixture)){
    & python (Join-Path $repository 'native\tests\make_logo_fixture.py') $fixture
    if($LASTEXITCODE -ne 0){throw 'Could not generate the logo fixture. Install the backend Python requirements first.'}
}
$priorPath=$env:PATH
try{
    $env:APEX_NATIVE_TEST_ORIGIN=$ApiOrigin
    $env:PATH=$publish+';'+$priorPath
    Push-Location $repository
    try{
        & dotnet run --project native/tests/WindowsHosted/WindowsHosted.csproj -c Release "-p:ApexWindowsPublishDirectory=$publish" -- $fixture 'tmp/native-refresh/windows-native-acceptance.json'
        if($LASTEXITCODE -ne 0){throw 'Published Windows hosted component acceptance failed.'}
    }finally{Pop-Location}
}finally{$env:PATH=$priorPath;$env:APEX_NATIVE_TEST_ORIGIN=$priorOrigin}
