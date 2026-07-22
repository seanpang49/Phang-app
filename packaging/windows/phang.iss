; ============================================================================
;  Phang - Windows (WSL2) installer  --  Inno Setup script
; ============================================================================
;  Produces a single one-click Phang-<ver>-Windows-x64-Setup.exe, the Windows
;  analogue of the macOS .pkg.  Like the .pkg, it does the LIGHT setup at
;  install time and defers the heavy ~30 GB tool/database download to first
;  launch (the GUI shows its own resumable progress window).
;
;  What it does:
;    - lays down phang_setup.ps1 + wsl_setup.sh + icon into {app}
;    - runs phang_setup.ps1 -SkipBootstrap  (verify WSL2, create the `phang`
;      conda env inside WSL2, pip-install phang) - needs internet, a few minutes
;    - phang_setup.ps1 creates the Start-Menu / Desktop shortcuts
;    - first time the user opens Phang, the GUI downloads the tools + databases
;
;  BUILD (needs Inno Setup 6 - https://jrsoftware.org/isdl.php, or `winget
;  install JRSoftware.InnoSetup`):
;      iscc packaging\windows\phang.iss
;  Output: packaging\windows\out\Phang-0.2.8-Windows-x64-Setup.exe
;
;  This beta is UNSIGNED, so Windows SmartScreen will warn on first run
;  ("More info" -> "Run anyway").  Add a code-signing certificate later to
;  drop that prompt (see README.md).
; ============================================================================

#define AppVer "0.2.8"

[Setup]
AppId={{9B2C7F1A-3D5E-4A9B-9C21-0A1B2C3D4E5F}
AppName=Phang
AppVersion={#AppVer}
AppPublisher=Phang
AppPublisherURL=https://github.com/seanpang49/Phang-app
DefaultDirName={autopf}\Phang
DefaultGroupName=Phang
DisableProgramGroupPage=yes
OutputDir=out
OutputBaseFilename=Phang-{#AppVer}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; WSL2 + WSLg + CUDA passthrough are 64-bit Windows 10/11 only.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=..\..\phang\gui\assets\icon.ico
UninstallDisplayIcon={app}\icon.ico
DisableWelcomePage=no
LicenseFile=..\..\LICENSE

[Messages]
WelcomeLabel2=This installs Phang, a phage-genome analysis app.%n%nPhang's tools are Linux-only, so they run inside WSL2 (Windows Subsystem for Linux). Setup will check WSL2 is present and prepare Phang inside it. The first time you open Phang it downloads ~30 GB of tools and databases, so keep a fast internet connection and ~40 GB free.%n%nWindows 11 is recommended (its built-in WSLg shows the Phang window).

[Files]
Source: "phang_setup.ps1";                 DestDir: "{app}"; Flags: ignoreversion
Source: "wsl_setup.sh";                     DestDir: "{app}"; Flags: ignoreversion
Source: "README.md";                        DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\phang\gui\assets\icon.ico";  DestDir: "{app}"; DestName: "icon.ico"; Flags: ignoreversion

[Run]
; Prepare WSL2 + the phang conda env now; defer the 30 GB download to first launch.
; phang_setup.ps1 also creates the Start-Menu / Desktop shortcuts.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\phang_setup.ps1"" -SkipBootstrap -NonInteractive"; \
  StatusMsg: "Preparing Phang inside WSL2 (this needs internet and a few minutes)..."; \
  Flags: waituntilterminated

[UninstallDelete]
; Remove the launcher assets and the shortcuts phang_setup.ps1 created.
; NOTE: user data (~/.phang inside WSL2, ~30 GB) is intentionally left in place.
;       To reclaim it, run inside WSL2:  rm -rf ~/.phang ~/.phang-setup
Type: filesandordirs; Name: "{localappdata}\Phang"
Type: files;          Name: "{autodesktop}\Phang.lnk"
Type: files;          Name: "{userprograms}\Phang.lnk"
