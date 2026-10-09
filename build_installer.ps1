$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$projectPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $projectPython)) {
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $systemPython) {
        throw "Python was not found. Install Python 3.13 and re-run this script."
    }

    & $systemPython.Source -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the project virtual environment."
    }

    $projectPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    & $projectPython -m pip install --upgrade pip
    & $projectPython -m pip install -r (Join-Path $projectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install the project Python dependencies."
    }
}

& $projectPython -c "import PyInstaller"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed in the project environment. Activate the environment and run 'python -m pip install -r requirements.txt'."
}

& $projectPython -m PyInstaller --noconfirm --clean --distpath (Join-Path $projectRoot "dist") --workpath (Join-Path $projectRoot "build") (Join-Path $projectRoot "DockPaste.spec")
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
& $innoCompiler (Join-Path $projectRoot "installer\DockPaste.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

Write-Host "DockPaste installer created in dist\installer."