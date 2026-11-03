# Sets Brushtalk up on this PC, or repairs and updates it. Run it again any time: it only does what's missing.
# Double-click "Set up Brushtalk.cmd" to run it.
#   -NoShortcuts   leaves the Start menu and desktop alone, for trying out a copy
#   -SkipWhisper   doesn't download the speech model now; it downloads on the first recording instead
param([switch]$NoShortcuts, [switch]$SkipWhisper)

# Not 'Stop': Windows PowerShell treats anything a program writes to its error stream as a failure, and pip and py write
# ordinary progress there. Each step checks its own exit code instead.
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
Set-Location -LiteralPath $root
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

function Step([string]$text) { Write-Host ''; Write-Host "== $text" -ForegroundColor Cyan }
function Good([string]$text) { Write-Host "   $text" -ForegroundColor Green }
function Note([string]$text) { Write-Host "   $text" -ForegroundColor Yellow }
function Quit-Setup([string]$text) { Write-Host "   $text" -ForegroundColor Red; exit 1 }

Write-Host "Setting up Brushtalk in $root"

Step 'Windows'
$build = [Environment]::OSVersion.Version.Build
if ($build -ge 22000) { Good "Windows 11 (build $build)" } else { Note "Windows build $build. Brushtalk is made for Windows 11, and may not work here." }

Step 'Python 3.13'
function Find-Python {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & $launcher.Source -3.13 -c 'import sys' 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ Exe = $launcher.Source; Args = @('-3.13') } }
    }
    # Where the installer puts it, for when this window started before it was installed.
    foreach ($place in "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe", "$env:ProgramFiles\Python313\python.exe") {
        if (Test-Path -LiteralPath $place) { return @{ Exe = $place; Args = @() } }
    }
    return $null
}
$python = Find-Python
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Quit-Setup 'Python 3.13 is needed. Install it from python.org (3.13, 64-bit), then run this again.'
    }
    Note "Python 3.13 isn't on this PC. Installing it with Windows' own installer, winget..."
    winget install --id Python.Python.3.13 --exact --scope user
    $python = Find-Python
    if (-not $python) { Quit-Setup "Python 3.13 still can't be found. Close this window, then run setup again." }
}
Good "Found $($python.Exe)"

Step "Brushtalk's own Python, and what it needs"
$venv = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    & $python.Exe @($python.Args) -m venv .venv
    if ($LASTEXITCODE -ne 0) { Quit-Setup "Making Brushtalk's own Python failed." }
}
Write-Host '   The first time, this downloads about 1.2 GB, most of it for the graphics card, so it can take a while.'
# constraints.txt holds the exact versions it was tested with, so this PC gets the same ones.
& $venv -m pip install --disable-pip-version-check -r requirements.txt -c constraints.txt
if ($LASTEXITCODE -ne 0) { Quit-Setup 'Installing what Brushtalk needs failed. Check the internet connection, then run setup again.' }
Good 'Installed.'

if (-not $SkipWhisper) {
    Step 'Whisper, the speech model'
    & $venv -m brushtalk --get-whisper
    if ($LASTEXITCODE -ne 0) { Note 'It will try again the first time you record.' }
}

if (-not $NoShortcuts) {
    Step 'Shortcuts in the Start menu and on the desktop'
    & $venv -m brushtalk --install-shortcuts
}

Step 'What Brushtalk sees on this PC'
& $venv -m brushtalk --check

$found = & $venv -c "from brushtalk import notes; print('codex' if notes.find_codex() else '-'); print('claude' if notes.find_claude() else '-')"
if ($found -notcontains 'codex' -or $found -notcontains 'claude') {
    Step 'For notes, prompts, code and proofreading'
    Write-Host '   Brushtalk records and transcribes on its own. Writing notes and prompts needs Codex, with a paid ChatGPT plan'
    Write-Host '   (Plus or above), or Claude Code, with a paid Claude plan (Pro or above). One of them is enough.'
    if ($found -notcontains 'codex') {
        Write-Host ''
        Write-Host '   To use Codex, run these one at a time in a new PowerShell window. The last one opens the browser to sign in:'
        Write-Host '      winget install --id OpenJS.NodeJS.LTS --exact' -ForegroundColor White
        Write-Host '      (then close that window and open a new one)'
        Write-Host '      npm install -g @openai/codex' -ForegroundColor White
        Write-Host '      codex login' -ForegroundColor White
    }
    if ($found -notcontains 'claude') {
        Write-Host ''
        # Its installer doesn't add its folder to the PATH, so typing claude alone won't work: the full path does.
        Write-Host '   To use Claude Code, run these in a new PowerShell window. The second one starts it, and the first time it'
        Write-Host '   opens the browser to sign in. Type /exit when that has worked.'
        Write-Host '      irm https://claude.ai/install.ps1 | iex' -ForegroundColor White
        Write-Host '      & "$env:USERPROFILE\.local\bin\claude.exe"' -ForegroundColor White
    }
    Write-Host ''
    Write-Host '   Then run setup again, to check.'
}

Step 'Done'
if ($NoShortcuts) {
    Good "Start it with: $root\.venv\Scripts\pythonw.exe -m brushtalk"
} else {
    Good 'Open Brushtalk from the Start menu or the desktop. It lives in the tray, by the clock.'
}
