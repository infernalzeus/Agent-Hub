@echo off
REM Double-click this to turn whatever is in this folder into installers.
REM
REM   Build-Release.cmd            build + compile the Windows installer, locally
REM   Build-Release.cmd /all       ... then tag and push, so GitHub Actions builds
REM                                the macOS .dmg and Linux .tar.gz too
REM
REM Windows is built here because you can test it immediately. macOS and Linux
REM cannot be cross-compiled, so they are built on GitHub's runners and collected
REM into the same draft release.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\Build-Release.ps1" %*
echo.
pause
