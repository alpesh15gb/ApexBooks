param(
    [ValidateSet('Windows','Android','All')][string]$Target = 'All',
    [ValidateSet('Debug','Release')][string]$Configuration = 'Release',
    [string]$JdkPath = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$deliverables = Join-Path $repository 'deliverables'
New-Item -ItemType Directory -Path $deliverables -Force | Out-Null
function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Build command failed: $Executable" }
}
Push-Location $repository
try {
    Invoke-Checked 'python' @('native/tools/check_api_routes.py')
    if ($Target -in @('Windows','All')) {
        $staging = '.native-build\publish\windows-' + $Configuration + '-' + [Guid]::NewGuid().ToString('N')
        $output = Join-Path (Join-Path $repository $staging) 'win-x64'
        $buildOutput = Join-Path $repository '.native-build\windows\'
        Invoke-Checked 'dotnet' @('publish','native/windows/ApexBooks.Windows.csproj','-c',$Configuration,'-r','win-x64','--self-contained','true','-p:Platform=x64','-p:WindowsAppSDKSelfContained=true',('-p:BaseOutputPath=' + $buildOutput),'-o',$output,'-v:minimal')
        & (Join-Path $PSScriptRoot 'Package-Windows.ps1') -PublishDirectory $output -Configuration $Configuration
    }
    if ($Target -in @('Android','All')) {
        if (-not $JdkPath) {
            $candidate = Get-ChildItem -LiteralPath 'C:\Program Files\Microsoft' -Directory -Filter 'jdk-21*' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($candidate) { $JdkPath = $candidate.FullName }
        }
        if (-not $JdkPath -or -not (Test-Path -LiteralPath (Join-Path $JdkPath 'bin\java.exe'))) { throw 'Android builds need JDK 21. Pass -JdkPath or set JAVA_HOME.' }
        $prior = @{}
        foreach ($name in @('JAVA_HOME','JAVA_TOOL_OPTIONS','APEX_ANDROID_KEYSTORE','APEX_ANDROID_STORE_PASSWORD','APEX_ANDROID_KEY_ALIAS','APEX_ANDROID_KEY_PASSWORD')) { $prior[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
        try {
            $env:JAVA_HOME = $JdkPath
            # OpenJDK falls back to TCP when a Windows UNIX-socket path is unavailable.
            # This path is deliberately never created; no machine setting is changed.
            $socketFallback = Join-Path $env:LOCALAPPDATA ('ApexBuild\no-unix-' + [Guid]::NewGuid().ToString('N'))
            $env:JAVA_TOOL_OPTIONS = ($prior['JAVA_TOOL_OPTIONS'] + ' -Djdk.net.unixdomain.tmpdir="' + $socketFallback + '"').Trim()
            if ($Configuration -eq 'Release' -and -not $env:APEX_ANDROID_KEYSTORE) {
                $file = Join-Path $env:LOCALAPPDATA 'ApexBooksNative\Signing\signing.dpapi'
                if (-not (Test-Path -LiteralPath $file)) { throw 'Create a private signing identity with Initialize-AndroidSigning.ps1 before building a release.' }
                $secure = ConvertTo-SecureString ((Get-Content -LiteralPath $file -Raw).Trim())
                $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
                try { $identity = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) | ConvertFrom-Json } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
                $env:APEX_ANDROID_KEYSTORE = $identity.store
                $env:APEX_ANDROID_KEY_ALIAS = $identity.alias
                $env:APEX_ANDROID_STORE_PASSWORD = $identity.password
                $env:APEX_ANDROID_KEY_PASSWORD = $identity.password
            }
            Push-Location (Join-Path $repository 'native\android')
            try { Invoke-Checked '.\gradlew.bat' @('--no-daemon',(':app:assemble' + $Configuration)) } finally { Pop-Location }
            $flavor = $Configuration.ToLowerInvariant()
            $apk = Join-Path $repository "native\android\app\build\outputs\apk\$flavor\app-$flavor.apk"
            $androidProject = Get-Content -LiteralPath (Join-Path $repository 'native\android\app\build.gradle.kts') -Raw
            $releaseVersion = [regex]::Match($androidProject,'versionName\s*=\s*"([^"]+)"').Groups[1].Value
            $destination = Join-Path $deliverables "Apex-Books-Android-$releaseVersion-$Configuration.apk"
            Copy-Item -LiteralPath $apk -Destination $destination -Force
            Get-FileHash -LiteralPath $destination -Algorithm SHA256 | Select-Object Path, Hash
        } finally {
            foreach ($name in $prior.Keys) { [Environment]::SetEnvironmentVariable($name,$prior[$name],'Process') }
            $identity = $null
        }
    }
} finally { Pop-Location }
