<#
.SYNOPSIS
    Phang - Windows (WSL2) one-click setup.  The Windows analogue of the macOS
    .pkg: it prepares WSL2, installs phang inside it, downloads the tools +
    databases, and creates Start-Menu / Desktop launchers.

.DESCRIPTION
    Execution model (Model A): everything runs INSIDE WSL2 - Python, phang, the
    9 Bioconda tool-envs, and the Tkinter GUI (shown on the Windows desktop via
    WSLg).  The Windows side is only a launcher.  This script:

      1. Verifies WSL2 + an Ubuntu distribution (guides `wsl --install` if absent).
      2. Copies wsl_setup.sh into the WSL2 native filesystem.
      3. Runs it: create the `phang` conda env, install phang, and (unless
         -SkipBootstrap) bootstrap the ~30 GB of tools + databases into ~/.phang.
      4. Creates Start-Menu and Desktop shortcuts that launch `phang gui`.

    Safe to re-run - every step is idempotent and resumable.

.PARAMETER SkipBootstrap
    Set up phang but DON'T download the ~30 GB now - defer it to the first GUI
    launch (the GUI shows its own resumable progress window, exactly like macOS).

.PARAMETER PhangSrc
    Override the phang source: a path or a "git+https://..." URL that pip installs.
    Defaults to a local source tree if this script sits inside the repo,
    otherwise the public GitHub repo.

.PARAMETER NonInteractive
    Never pause for input (for unattended / installer-driven runs).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File phang_setup.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File phang_setup.ps1 -SkipBootstrap
#>
[CmdletBinding()]
param(
    [switch]$SkipBootstrap,
    [switch]$NonInteractive,
    [string]$PhangSrc = ""
)

$ErrorActionPreference = "Stop"
# Make `wsl.exe` emit UTF-8 instead of UTF-16LE so PowerShell 5.1 parses it.
$env:WSL_UTF8 = "1"

$EnvName = "phang"
$WslSetupDir = '$HOME/.phang-setup'   # native WSL2 location (single-quoted: expanded by bash, not PS)

# ---------------------------------------------------------------------------
# Helpers (defined first - PowerShell resolves functions at call time, top-down).
# ---------------------------------------------------------------------------
function Info($m) { Write-Host "==> $m"    -ForegroundColor Cyan }
function Good($m) { Write-Host "  ok: $m"  -ForegroundColor Green }
function Warn($m) { Write-Host "  warn: $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }
function Pause-IfInteractive {
    if (-not $NonInteractive) { Read-Host "`nPress Enter to close" | Out-Null }
}
function Have-Command($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
function ConvertTo-WslPath($winPath) {
    $full = (Resolve-Path $winPath).Path
    $drive = $full.Substring(0,1).ToLower()
    $rest = $full.Substring(2) -replace "\\","/"
    "/mnt/$drive$rest"
}
function Get-WslDistros {
    try { $out = & wsl.exe --list --quiet 2>$null } catch { return @() }
    if (-not $out) { return @() }
    $out | ForEach-Object { ($_ -replace "[^\x20-\x7E]","").Trim() } | Where-Object { $_ -ne "" }
}

Write-Host ""
Write-Host "  Phang - Phage Genome Analysis  |  Windows (WSL2) setup" -ForegroundColor White
Write-Host "  ----------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# ---------------------------------------------------------------------------
# 0. Locate the WSL2 setup script that ships next to this file.
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$WslSetupSh = Join-Path $ScriptDir "wsl_setup.sh"
if (-not (Test-Path $WslSetupSh)) {
    Fail "wsl_setup.sh not found next to this script ($ScriptDir). Re-download the installer."
}

# If this script lives inside a phang source tree, install phang from that tree
# (deterministic); otherwise fall back to the public repo.
if ([string]::IsNullOrEmpty($PhangSrc)) {
    $RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
    if (Test-Path (Join-Path $RepoRoot "pyproject.toml")) {
        $PhangSrc = ConvertTo-WslPath $RepoRoot
    } else {
        $PhangSrc = "git+https://github.com/seanpang49/Phang-app.git"
    }
}

# ---------------------------------------------------------------------------
# 1. WSL2 present?
# ---------------------------------------------------------------------------
Info "Checking for WSL2..."
if (-not (Have-Command "wsl.exe")) {
    Warn "WSL is not installed on this PC."
    Write-Host ""
    Write-Host "  Phang's analysis tools are Linux-only (Bioconda), so they run inside" -ForegroundColor Gray
    Write-Host "  WSL2 (Windows Subsystem for Linux). To install it:" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    1. Open PowerShell as Administrator" -ForegroundColor White
    Write-Host "    2. Run:  wsl --install" -ForegroundColor White
    Write-Host "    3. Restart your PC, finish the Ubuntu user setup, then re-run this installer." -ForegroundColor White
    Write-Host ""
    if ((Test-Admin) -and -not $NonInteractive) {
        $ans = Read-Host "Install WSL2 + Ubuntu now? (requires a reboot afterwards) [y/N]"
        if ($ans -match '^(y|yes)$') {
            Info "Running: wsl --install"
            & wsl.exe --install
            Warn "Reboot your PC, complete the Ubuntu setup, then run this installer again."
        }
    }
    Pause-IfInteractive
    exit 1
}

$distros = Get-WslDistros
if ($distros.Count -eq 0) {
    Warn "WSL is present but no Linux distribution is installed."
    Info "Installing Ubuntu (this may need a reboot to finish)..."
    try { & wsl.exe --install -d Ubuntu } catch { }
    Warn "If prompted, reboot and complete the Ubuntu user setup, then re-run this installer."
    Pause-IfInteractive
    exit 1
}
Good ("WSL2 ready. Distributions: " + ($distros -join ", "))

# Confirm the default distro is version 2 (WSLg + CUDA passthrough need v2).
try {
    $verTable = & wsl.exe --list --verbose 2>$null | ForEach-Object { ($_ -replace "[^\x20-\x7E]","").Trim() }
    if ($verTable -match '\* .*\s1\s*$') {
        Warn "Your default WSL distro is version 1. Phang needs WSL2. Convert it with:"
        Warn "    wsl --set-version <DistroName> 2"
    }
} catch { }

# GPU note (informational - the pipeline auto-detects and falls back to CPU).
try {
    $gpu = & wsl.exe -- bash -lc "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1"
    if ($gpu) { Good "NVIDIA GPU visible in WSL2: $($gpu.Trim()) (CUDA acceleration available)" }
    else      { Warn "No NVIDIA GPU visible in WSL2 - the pipeline will use CPU (slower but fine)." }
} catch { }

# ---------------------------------------------------------------------------
# 2. Copy wsl_setup.sh into the WSL2 native filesystem (CRLF-stripped).
# ---------------------------------------------------------------------------
Info "Staging the setup script inside WSL2..."
# Read the file byte-exact from its /mnt path inside WSL (single-quoted so paths
# with spaces like "Program Files" are safe), strip CR, write to WSL2 native FS.
$WslSrc = ConvertTo-WslPath $WslSetupSh
& wsl.exe -- bash -c "mkdir -p $WslSetupDir && tr -d '\r' < '$WslSrc' > $WslSetupDir/wsl_setup.sh && chmod +x $WslSetupDir/wsl_setup.sh"
if ($LASTEXITCODE -ne 0) { Fail "Could not copy wsl_setup.sh into WSL2." }
Good "Setup script staged at ~/.phang-setup/wsl_setup.sh"

# ---------------------------------------------------------------------------
# 3. Run the install (+ bootstrap unless skipped).  Output streams live.
# ---------------------------------------------------------------------------
if ($SkipBootstrap) { $mode = "install" } else { $mode = "all" }
Info "Installing phang inside WSL2 (mode: $mode; source: $PhangSrc)..."
if (-not $SkipBootstrap) {
    Warn "First run downloads ~30 GB of tools + databases. This can take 15-60+ minutes."
    Warn "It is resumable - if it stops, just run this installer again."
}
Write-Host ""

& wsl.exe -- bash -lc "export PHANG_SRC='$PhangSrc' && bash $WslSetupDir/wsl_setup.sh $mode"
if ($LASTEXITCODE -ne 0) {
    Fail "WSL2 setup failed (exit $LASTEXITCODE). Re-run this installer to resume, or see the console output above."
}
Write-Host ""
Good "phang is installed inside WSL2."

# ---------------------------------------------------------------------------
# 4. Create Start-Menu + Desktop launchers.
# ---------------------------------------------------------------------------
Info "Creating launchers..."
$AppDir = Join-Path $env:LOCALAPPDATA "Phang"
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

# Copy an icon if one ships with the source tree.
$IconSrc = Join-Path $ScriptDir "..\..\phang\gui\assets\icon.ico"
$IconPath = $null
if (Test-Path $IconSrc) {
    $IconPath = Join-Path $AppDir "icon.ico"
    Copy-Item $IconSrc $IconPath -Force
}

# A .bat launcher (also handy to pin / double-click directly).
$BatPath = Join-Path $AppDir "Phang.bat"
@"
@echo off
REM Phang - Phage Genome Analysis Pipeline (Windows/WSL2 launcher)
wsl.exe -- bash -lc "bash $WslSetupDir/wsl_setup.sh gui"
"@ | Set-Content -Path $BatPath -Encoding ASCII

function New-Shortcut($linkPath) {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($linkPath)
    $sc.TargetPath = "$env:SystemRoot\System32\wsl.exe"
    $sc.Arguments  = "-- bash -lc ""bash $WslSetupDir/wsl_setup.sh gui"""
    $sc.Description = "Phang - Phage Genome Analysis Pipeline"
    $sc.WindowStyle = 7   # start the wsl.exe console minimized; the GUI opens via WSLg
    if ($IconPath) { $sc.IconLocation = $IconPath }
    $sc.Save()
}

$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
New-Shortcut (Join-Path $StartMenu "Phang.lnk")
$Desktop = [Environment]::GetFolderPath("Desktop")
New-Shortcut (Join-Path $Desktop "Phang.lnk")
Good "Shortcuts created (Start Menu + Desktop) and launcher at $BatPath"

# ---------------------------------------------------------------------------
# 5. Done.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Phang is ready." -ForegroundColor Green
if ($SkipBootstrap) {
    Write-Host "  The first time you open Phang it will download its tools + databases (~30 GB)." -ForegroundColor Gray
}
Write-Host "  Launch it from the Start Menu (search 'Phang') or the Desktop shortcut." -ForegroundColor Gray
Write-Host ""
Pause-IfInteractive
