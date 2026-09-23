@echo off
REM Double-click this. A dialog opens: type the patch notes, tick the platforms,
REM press COMPILE. Nothing to type on a command line.
REM
REM   Build-Release.cmd          open the build dialog
REM   Build-Release.cmd --cli    skip the dialog (scripted/CI use; see BUILDING.md)
REM
REM Only one Agent Hub runs at a time: every install uses port 8081 and
REM %LOCALAPPDATA%\AgentHub\state. Close the source Hub before testing an install.
setlocal
cd /d "%~dp0"
if /i "%~1"=="--cli" (
  shift
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\Build-Release.ps1" %*
) else (
  REM -STA is required for WinForms dialogs.
  powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0packaging\Build-Release-UI.ps1" %*
)
echo.
pause
