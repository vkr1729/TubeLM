@echo off
REM scripts/build_win_app.bat - Compiles and bundles TubeLM into a native Windows Application
echo =========================================================================
echo                   TubeLM Windows App Bundler Wizard
echo =========================================================================

REM Navigate to desktop directory (where the spec file lives)
cd /d "%~dp0\.."
set "REPO_ROOT=%~dp0\..\.."

REM Ensure venv exists at repo root (not inside desktop\)
if not exist "%REPO_ROOT%\.venv" (
    echo Creating Python virtual environment at %REPO_ROOT%\.venv ...
    python -m venv "%REPO_ROOT%\.venv"
)

REM Upgrade pip and install GUI dependencies into repo root venv
echo Upgrading pip and installing GUI dependencies...
"%REPO_ROOT%\.venv\Scripts\pip.exe" install --upgrade pip
"%REPO_ROOT%\.venv\Scripts\pip.exe" install -r requirements.txt -r requirements-gui.txt

REM Run PyInstaller using the Windows spec file (single source of truth)
echo.
echo Compiling TubeLM tray application using PyInstaller spec (tubelm_win.spec)...
"%REPO_ROOT%\.venv\Scripts\pyinstaller.exe" --clean tubelm_win.spec

echo.
echo =========================================================================
echo              Application Compiled Successfully!
echo =========================================================================
echo You can locate your native Windows App executable here:
echo     %CD%\dist\TubeLM\TubeLM.exe
echo.
echo To run your application, simply double-click TubeLM.exe!
echo.
