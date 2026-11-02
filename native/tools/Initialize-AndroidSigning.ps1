param([string]$JdkPath = $env:JAVA_HOME)
$ErrorActionPreference = 'Stop'
$signingDirectory = Join-Path $env:LOCALAPPDATA 'ApexBooksNative\Signing'
$keyFile = Join-Path $signingDirectory 'apex-books-release.jks'
$credentialFile = Join-Path $signingDirectory 'signing.dpapi'
if ((Test-Path -LiteralPath $keyFile) -or (Test-Path -LiteralPath $credentialFile)) {
    if ((Test-Path -LiteralPath $keyFile) -and (Test-Path -LiteralPath $credentialFile)) {
        Write-Output 'The existing private Android signing identity is ready.'
        return
    }
    throw 'Only part of the signing identity exists. Restore its matching protected credential or keystore; do not replace the key.'
}
$keytool = Join-Path $JdkPath 'bin\keytool.exe'
if (-not (Test-Path -LiteralPath $keytool)) { throw 'Pass -JdkPath pointing to an installed JDK.' }
New-Item -ItemType Directory -Path $signingDirectory -Force | Out-Null
$random = New-Object byte[] 36
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $generator.GetBytes($random) } finally { $generator.Dispose() }
$password = [Convert]::ToBase64String($random)
$previousStore = $env:APEX_ANDROID_STORE_PASSWORD
$previousKey = $env:APEX_ANDROID_KEY_PASSWORD
try {
    $env:APEX_ANDROID_STORE_PASSWORD = $password
    $env:APEX_ANDROID_KEY_PASSWORD = $password
    & $keytool -genkeypair -keystore $keyFile -alias apex-books-release -keyalg RSA -keysize 4096 -sigalg SHA256withRSA -validity 9125 -dname 'CN=Apex Books, O=Apex Books, C=IN' -storepass:env APEX_ANDROID_STORE_PASSWORD -keypass:env APEX_ANDROID_KEY_PASSWORD -noprompt
    if ($LASTEXITCODE -ne 0) { throw 'Android signing key creation failed.' }
    $credential = @{ store = $keyFile; alias = 'apex-books-release'; password = $password } | ConvertTo-Json -Compress
    $secure = ConvertTo-SecureString -String $credential -AsPlainText -Force
    ConvertFrom-SecureString -SecureString $secure | Set-Content -LiteralPath $credentialFile -Encoding ASCII
    Write-Output 'Created a private Android signing identity outside the repository. Its password is protected for this Windows account.'
} finally {
    $env:APEX_ANDROID_STORE_PASSWORD = $previousStore
    $env:APEX_ANDROID_KEY_PASSWORD = $previousKey
    $password = $null
    $credential = $null
    [Array]::Clear($random, 0, $random.Length)
}
