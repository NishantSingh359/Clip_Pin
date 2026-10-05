$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$pyinstallerCommand = Get-Command pyinstaller -ErrorAction SilentlyContinue
$pyinstaller = if ($pyinstallerCommand) {
    $pyinstallerCommand.Source
} else {
    Join-Path $projectRoot ".venv\Scripts\pyinstaller.exe"
}

if (-not (Test-Path $pyinstaller)) {
    throw "PyInstaller was not found. Activate the project environment and install the project requirements first."
}

& $pyinstaller --noconfirm --clean --distpath (Join-Path $projectRoot "dist") --workpath (Join-Path $projectRoot "build") (Join-Path $projectRoot "ClipFlow.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$innoCandidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $innoCandidates) {
    throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php and run this script again."
}

$innoCompiler = $innoCandidates | Select-Object -First 1
& $innoCompiler (Join-Path $projectRoot "installer\ClipFlow.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

Write-Host "Installer created in dist\installer."