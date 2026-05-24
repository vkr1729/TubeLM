@echo off
REM scripts/build_win_app.bat - Compiles and bundles TubeLM into a native Windows Application
echo =========================================================================
echo                   TubeLM Windows App Bundler Wizard
echo =========================================================================

REM Navigate to project root
cd /d "%~dp0\.."

REM Ensure venv exists
if not exist .venv (
    echo Creating Python virtual environment venv...
    python -m venv .venv
)

REM Activate environment and verify dependencies
echo Upgrading pip and installing GUI dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-gui.txt

REM Run PyInstaller compilation
echo.
echo Compiling TubeLM tray application using PyInstaller...
pyinstaller ^
    --noconsole ^
    --clean ^
    --name="TubeLM" ^
    --icon="assets\logo.ico" ^
    --add-data "templates;templates" ^
    --add-data "assets;assets" ^
    --add-data "Summary_Prompt.md;." ^
    --add-data "Podcast_Prompt.md;." ^
    win_launcher.py

echo.
echo =========================================================================
echo              Application Compiled Successfully!
echo =========================================================================
echo You can locate your native Windows App executable here:
echo     %CD%\dist\TubeLM\TubeLM.exe
echo.
echo To run your application, simply double-click TubeLM.exe!
echo.
