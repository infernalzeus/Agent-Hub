@echo off
REM Double-click this to turn whatever is in this folder into a real installer.
REM
REM   Build-Release.cmd            build Agent-Hub-Setup.exe - the real installer,
REM                                for you to install and test
REM   Build-Release.cmd /testonly  build a throwaway that installs as a separate
REM                                "Agent Hub Test" and cannot be mistaken for the
REM                                real thing
REM   Build-Release.cmd /all       publish: needs a completed release-evidence file
REM
REM Only one Agent Hub runs at a time: every install uses port 8081 and
REM %LOCALAPPDATA%\AgentHub\state. Close the source Hub before testing an install.
REM
REM Windows is built here so you can test it immediately. macOS and Linux cannot be
REM cross-compiled, so they are built on GitHub's runners - see packaging\BUILDING.md.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\Build-Release.ps1" %*
echo.
pause
