@echo off
REM ===========================================================================
REM  Phang - Windows (WSL2) installer  ·  one-click entry point
REM ===========================================================================
REM  Double-click this file to install Phang. It runs phang_setup.ps1 (in the
REM  same folder) with an execution-policy bypass so you don't have to change
REM  any PowerShell settings.
REM
REM  Options (advanced): pass -SkipBootstrap to defer the ~30 GB download to the
REM  first time you open Phang, e.g.:   Install-Phang.bat -SkipBootstrap
REM ===========================================================================
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%phang_setup.ps1" %*
echo.
pause
