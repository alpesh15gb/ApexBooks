param([switch]$PrepareQaSession,[string]$Serial='emulator-5554',[ValidatePattern('^[A-Za-z0-9_.]+$')][string]$TestClass)
$ErrorActionPreference='Stop'
if($Serial -notmatch '^emulator-[0-9]+$'){throw 'Use a dedicated QA emulator for hosted component acceptance.'}
$repository=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$names=@('JAVA_HOME','JAVA_TOOL_OPTIONS','ANDROID_SERIAL','APEX_ANDROID_KEYSTORE','APEX_ANDROID_STORE_PASSWORD','APEX_ANDROID_KEY_ALIAS','APEX_ANDROID_KEY_PASSWORD')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try{
    $env:ANDROID_SERIAL=$Serial
    $env:JAVA_HOME=(Get-ChildItem -LiteralPath 'C:\Program Files\Microsoft' -Directory -Filter 'jdk-21*'|Select-Object -First 1).FullName
    $fallback=Join-Path $env:LOCALAPPDATA ('ApexBuild\no-unix-'+[Guid]::NewGuid().ToString('N'))
    $env:JAVA_TOOL_OPTIONS=($prior['JAVA_TOOL_OPTIONS']+' -Djdk.net.unixdomain.tmpdir="'+$fallback+'"').Trim()
    if(-not $env:APEX_ANDROID_KEYSTORE){
        $file=Join-Path $env:LOCALAPPDATA 'ApexBooksNative\Signing\signing.dpapi'
        $secure=ConvertTo-SecureString ([IO.File]::ReadAllText($file).Trim())
        $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try{$identity=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)|ConvertFrom-Json}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}
        $env:APEX_ANDROID_KEYSTORE=$identity.store;$env:APEX_ANDROID_KEY_ALIAS=$identity.alias
        $env:APEX_ANDROID_STORE_PASSWORD=$identity.password;$env:APEX_ANDROID_KEY_PASSWORD=$identity.password
    }
    Push-Location (Join-Path $repository 'native\android')
    try{
        # Keep the target app/data at teardown. This test must never erase a remembered session.
        $arguments=@('--no-daemon','-PapexTestBuildType=release','-Pandroid.injected.androidTest.leaveApksInstalledAfterRun=true',':app:connectedReleaseAndroidTest')
        if($PrepareQaSession){$arguments+='-PapexKeepQaSession=true'}
        if($TestClass){$arguments+='-Pandroid.testInstrumentationRunnerArguments.class='+$TestClass}
        & .\gradlew.bat @arguments
        if($LASTEXITCODE -ne 0){throw 'Android hosted component acceptance failed.'}
        Write-Output 'Component checks passed. Build/install the normal release with Build-Native.ps1 before distribution; the test host uses test-only R8 retention.'
    }finally{Pop-Location}
}finally{foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name],'Process')};$identity=$null}
