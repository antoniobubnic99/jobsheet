# Builds the Windows ZIP: a folder the user unpacks and double-clicks.
#
# The point of this package is someone who has no Python, no Node, and no
# intention of acquiring either. So it carries its own interpreter -- the
# official embeddable build from python.org -- with every dependency and the
# built interface already inside it. Nothing is installed, nothing is signed
# up for, nothing costs anything.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build-windows-zip.ps1
#
# The order below is not arrangeable to taste:
#
#   1. the interface is built by Node into the Python package
#   2. the wheel is built around it
#   3. the wheel and its dependencies are installed into the package
#   4. the embedded interpreter is made to run the result -- BEFORE zipping
#
# Step 4 is the one people skip. It is also the one that has already caught a
# broken package in this project's predecessor, so it stays: the interpreter
# that runs on the user's machine is the only one whose opinion counts.

[CmdletBinding()]
param(
    # Must match the minor version of the Python running this script, because
    # the dependencies include compiled wheels (pydantic-core) that pip
    # resolves for the host interpreter.
    [string]$PythonVersion = '3.11.9',

    # For rebuilding the ZIP without waiting for npm again. The frontend must
    # already be built; the smoke test will catch it if it is not.
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is far faster without it

$Root      = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Build     = Join-Path $Root 'build'
$Cache     = Join-Path $Build 'cache'
$FolderName = 'JobSheet'
$Staging   = Join-Path $Build $FolderName
$AppDir    = Join-Path $Staging 'app'
$Runtime   = Join-Path $AppDir 'runtime'
$LibDir    = Join-Path $AppDir 'lib'
$Zip       = Join-Path $Build 'JobSheet-windows.zip'

$PythonZipName = "python-$PythonVersion-embed-amd64.zip"
$PythonUrl     = "https://www.python.org/ftp/python/$PythonVersion/$PythonZipName"

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "    $text" -ForegroundColor DarkGray }

# ---------------------------------------------------------------- 0. host check
$hostVersion = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
$wantMinor = ($PythonVersion -split '\.')[0..1] -join '.'
if ($hostVersion -ne $wantMinor) {
    throw @"
Python on PATH is $hostVersion, but this package embeds $wantMinor.

They have to match: JobSheet depends on pydantic, whose core is a compiled
extension, and pip resolves those wheels for the interpreter it is running
under. A mismatch produces a ZIP that fails on the user's machine with an
import error, not here.

Either run this from a $wantMinor environment, or pass -PythonVersion to embed
a build matching $hostVersion.
"@
}

# `build` and `hatchling` come from the dev extra, so a shell that has Python on
# PATH but not the project's environment activated gets here and then fails four
# steps later with "No module named build.__main__" -- which names the wrong
# problem. Ask now, while the answer is still one command.
#
# Asked through stdout rather than an exit code: a native command writing to
# stderr under $ErrorActionPreference = 'Stop' is its own Windows PowerShell
# trap, and this check must not become the thing that breaks the build.
#
# `origin` is what makes the test honest. This repository writes its output to
# a folder called `build`, and a folder without `__init__.py` on sys.path is a
# perfectly good namespace package -- so `find_spec('build')` is truthy even on
# an interpreter that has never heard of the build tool. Only a real package
# has an origin; a namespace portion has None. Getting this wrong is how
# `python -m build` comes to say "'build' is a package and cannot be directly
# executed", which is true, unhelpful, and about the wrong package entirely.
$hasBuild = & python -c "import importlib.util as u; s = u.find_spec('build'); print('yes' if s and s.origin else 'no')"
if ($hasBuild -ne 'yes') {
    throw @"
Python on PATH cannot import the "build" package, so the wheel cannot be built.
(A "build" folder in this repository is not it -- that is where output goes.)

This almost always means the project environment is not activated. From the
repository root:

    .venv\Scripts\Activate.ps1

or install the dev extra into whichever interpreter is on PATH:

    python -m pip install -e ".[dev]"
"@
}

# ---------------------------------------------------------------- 1. clean
Step 'Clearing the previous build'
if (Test-Path $Staging) { Remove-Item $Staging -Recurse -Force }
if (Test-Path $Zip) { Remove-Item $Zip -Force }
New-Item -ItemType Directory -Force -Path $AppDir, $Cache | Out-Null

# ---------------------------------------------------------------- 2. interface
if ($SkipFrontend) {
    Step 'Skipping the interface build (-SkipFrontend)'
} else {
    Step 'Building the interface'
    Push-Location (Join-Path $Root 'web')
    try {
        if (-not (Test-Path 'node_modules')) {
            Note 'installing npm dependencies'
            & npm ci
            if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
        }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'npm run build failed' }
    } finally { Pop-Location }
}

$indexHtml = Join-Path $Root 'src\jobsheet\web\index.html'
if (-not (Test-Path $indexHtml)) {
    throw "The interface is not built ($indexHtml is missing). Run without -SkipFrontend."
}

# ---------------------------------------------------------------- 3. wheel
Step 'Building the wheel'
Push-Location $Root
try {
    & python -m build --wheel
    if ($LASTEXITCODE -ne 0) { throw 'python -m build failed' }
} finally { Pop-Location }

$wheel = Get-ChildItem (Join-Path $Root 'dist\*.whl') |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $wheel) { throw 'No wheel was produced.' }
Note "using $($wheel.Name)"

# ---------------------------------------------------------------- 4. dependencies
Step 'Installing JobSheet and its dependencies into the package'
& python -m pip install --target $LibDir --upgrade $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw 'pip install --target failed' }

# ---------------------------------------------------------------- 5. interpreter
Step "Adding the embedded Python $PythonVersion"
$PythonZip = Join-Path $Cache $PythonZipName
if (-not (Test-Path $PythonZip)) {
    Note "downloading $PythonUrl"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonZip -UseBasicParsing
}
Expand-Archive -Path $PythonZip -DestinationPath $Runtime -Force

# The embeddable build ships a `._pth` that pins sys.path and switches off
# site. Without editing it, the interpreter cannot see the `lib` directory
# next door and nothing imports. Paths in it are relative to the runtime
# folder, which is why this is `..\lib` rather than an absolute path -- the
# user unpacks this wherever they like.
$pth = Get-ChildItem (Join-Path $Runtime 'python*._pth') | Select-Object -First 1
if (-not $pth) { throw 'No ._pth in the embeddable distribution; cannot set the import path.' }
$lines = Get-Content $pth.FullName
if ($lines -notcontains '..\lib') { $lines += '..\lib' }
# `import site` is commented out by default; .pth files in lib/ are not
# processed without it, and some dependencies rely on that.
$lines = $lines | ForEach-Object { if ($_ -eq '#import site') { 'import site' } else { $_ } }
Set-Content -Path $pth.FullName -Value $lines -Encoding ascii
Note "import path: $($pth.Name)"

# ---------------------------------------------------------------- 6. launcher
Step 'Writing the launcher'

# No diacritics anywhere in the .cmd: it runs in the OEM code page, where they
# arrive as mojibake. The chain below is deliberate -- the embedded runtime is
# tried first, and the two fallbacks exist for the single most common support
# question, which is a ZIP that was opened rather than extracted.
$launcher = @'
@echo off
rem JobSheet. This is the only file you need to run.
setlocal
chcp 65001 >nul
title JobSheet
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "EMBEDDED=%~dp0app\runtime\python.exe"

if exist "%EMBEDDED%" (
    "%EMBEDDED%" -m jobsheet.cli %*
    goto :done
)

rem Fallbacks, for a package whose runtime folder did not survive unpacking.
py -3 -c "import jobsheet" >nul 2>&1
if not errorlevel 1 (
    py -3 -m jobsheet.cli %*
    goto :done
)

python -c "import jobsheet" >nul 2>&1
if not errorlevel 1 (
    python -m jobsheet.cli %*
    goto :done
)

echo.
echo   The folder "app\runtime" is missing, so JobSheet has no Python to run.
echo.
echo   The usual cause: the ZIP was opened and one file dragged out of it,
echo   rather than extracted.
echo.
echo   Fix: right-click the ZIP, choose "Extract All", and run this file
echo   from the extracted folder.
echo.
pause

:done
endlocal
'@
Set-Content -Path (Join-Path $Staging 'Start JobSheet.cmd') -Value $launcher -Encoding ascii

$readme = @'
JobSheet
========

Collect job ads from anywhere. Get a spreadsheet you actually own.

To start: double-click "Start JobSheet.cmd". A browser window opens.
To stop:  close the black console window.

Nothing is installed on this computer. Everything JobSheet needs, including
its own copy of Python, is in the "app" folder next to this file. Move the
whole folder wherever you like; it does not mind.

Your data -- the jobs you have found, the notes you have written, which ones
you have applied to -- lives in your user folder, not in here, so replacing
this folder with a newer version does not lose any of it.

If nothing happens when you double-click:
  the ZIP was probably opened rather than extracted. Right-click it, choose
  "Extract All", and run "Start JobSheet.cmd" from the extracted folder.
'@
Set-Content -Path (Join-Path $Staging 'READ ME.txt') -Value $readme -Encoding utf8

# ---------------------------------------------------------------- 7. smoke test
# Everything above can succeed and still produce a package that does not run.
# This is the only step that asks the interpreter the user will actually use.
Step 'Checking the package with its own interpreter'
$embedded = Join-Path $Runtime 'python.exe'

$imports = & $embedded -c "import jobsheet, fastapi, uvicorn, openpyxl, pydantic, httpx; from jobsheet.api.app import web_is_built; print(jobsheet.__version__, web_is_built())"
if ($LASTEXITCODE -ne 0) { throw 'The embedded interpreter cannot import JobSheet.' }
Note "imports: $imports"
if ($imports -notmatch 'True') {
    throw 'The package has no interface in it -- web_is_built() said False.'
}

Note 'starting the server the way the launcher does'
$port = 8799
$home_ = Join-Path $Build 'smoke-home'
if (Test-Path $home_) { Remove-Item $home_ -Recurse -Force }
New-Item -ItemType Directory -Force -Path $home_ | Out-Null

# The child inherits this process's environment. `Start-Process -Environment`
# would be tidier but needs PowerShell 7.4, and this script has to run on the
# Windows PowerShell 5.1 that ships with Windows.
$previousHome = $env:JOBSHEET_HOME
$env:JOBSHEET_HOME = $home_
try {
    $server = Start-Process -FilePath $embedded `
        -ArgumentList '-m', 'jobsheet.cli', 'serve', '--no-browser', '--port', "$port" `
        -PassThru -NoNewWindow
} finally {
    $env:JOBSHEET_HOME = $previousHome
}

try {
    $up = $false
    foreach ($attempt in 1..30) {
        try {
            $health = Invoke-WebRequest "http://127.0.0.1:$port/api/health" -UseBasicParsing -TimeoutSec 2
            if ($health.StatusCode -eq 200) { $up = $true; break }
        } catch { Start-Sleep -Milliseconds 700 }
    }
    if (-not $up) { throw 'The packaged server never answered /api/health.' }
    Note "health: $($health.Content)"

    $page = Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 5
    if ($page.Content -match 'has not been built') {
        throw 'The packaged server served the placeholder page instead of the interface.'
    }
    Note 'the packaged server serves the interface'
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    if (Test-Path $home_) { Remove-Item $home_ -Recurse -Force -ErrorAction SilentlyContinue }
}

# ---------------------------------------------------------------- 8. tidy
# After the smoke test, not before: running the interpreter recreates these.
Step 'Removing __pycache__'
Get-ChildItem -Path $Staging -Recurse -Force -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $Staging -Recurse -Force -File -Filter '*.pyc' |
    Remove-Item -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- 9. zip
Step 'Compressing'
Compress-Archive -Path $Staging -DestinationPath $Zip -CompressionLevel Optimal

$mb = [math]::Round((Get-Item $Zip).Length / 1MB, 1)
Write-Host ''
Write-Host "Done: $Zip ($mb MB)" -ForegroundColor Green
Write-Host 'Unpack it and double-click "Start JobSheet.cmd".' -ForegroundColor Green
