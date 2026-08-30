param(
    [string]$OutputPath = "ColinTTS.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SourcePath = Join-Path $PSScriptRoot "windows_launcher\Program.cs"
$IconPath = Join-Path $ProjectRoot "src\omni_tts_shared\assets\colin_tts.ico"
$ResolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $ProjectRoot $OutputPath
}

$CompilerCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$Compiler = $CompilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (!$Compiler) {
    throw "The .NET Framework C# compiler was not found."
}
if (!(Test-Path -LiteralPath $IconPath)) {
    throw "Missing launcher icon: $IconPath"
}

$OutputDirectory = Split-Path -Parent $ResolvedOutput
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
& $Compiler /nologo /target:winexe /platform:anycpu /optimize+ "/win32icon:$IconPath" "/out:$ResolvedOutput" $SourcePath
if ($LASTEXITCODE -ne 0) {
    throw "Windows launcher compilation failed with exit code $LASTEXITCODE"
}

Write-Host "Windows launcher built: $ResolvedOutput"
