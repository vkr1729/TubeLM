# test_win_gui_e2e.ps1 — Automated E2E GUI Sandbox Test Orchestration for Windows Hosts.
# Run in PowerShell from project root: .\desktop\scripts\test_win_gui_e2e.ps1

Write-Host "=========================================================================" -ForegroundColor Cyan
Write-Host "             📦 TubeLM Windows Standalone E2E GUI Validator 📦           " -ForegroundColor Cyan
Write-Host "=========================================================================" -ForegroundColor Cyan

# Navigate to project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $ProjectDir

# Ensure venv exists
if (-not (Test-Path ".venv")) {
    Write-Host "[*] Creating virtual environment (.venv)..." -ForegroundColor Blue
    python -m venv .venv
}

# Activate environment and install dependencies
Write-Host "[*] Upgrading pip and installing dependencies..." -ForegroundColor Blue
& .venv\Scripts\pip.exe install --upgrade pip
& .venv\Scripts\pip.exe install -r requirements.txt -r requirements-gui.txt playwright requests

# Install Playwright browser
Write-Host "[*] Ensuring Playwright browser is installed..." -ForegroundColor Blue
& .venv\Scripts\playwright.exe install chromium

# Compile Standalone single-file executable
Write-Host "`n[*] Starting Standalone Executable compilation via build_win_app.bat..." -ForegroundColor Blue
& cmd.exe /c "desktop\scripts\build_win_app.bat"

# Verify standalone executable built
$ExePath = Join-Path $ProjectDir "dist\TubeLM.exe"
if (-not (Test-Path $ExePath)) {
    Write-Host "[!] Error: Standalone binary not found at $ExePath." -ForegroundColor Red
    Exit 1
}
Write-Host "✅ Standalone compiled: $ExePath" -ForegroundColor Green

# Launch Standalone background process on test port 5050
Write-Host "`n[*] Launching Standalone background GUI service on port 5050..." -ForegroundColor Blue
$ServerProcess = Start-Process -FilePath $ExePath -ArgumentList "--gui", "--port", "5050" -PassThru -NoNewWindow

# Wait for Flask server to boot
Start-Sleep -Seconds 4

# Run Playwright E2E Integration Suite
Write-Host "`n[*] Executing E2E Playwright DOM validation..." -ForegroundColor Blue
$TestScript = Join-Path $ProjectDir "desktop\scripts\test_gui_e2e.py"
& .venv\Scripts\python.exe $TestScript

# Cleanup background process
Write-Host "`n[*] Stopping background standalone GUI service..." -ForegroundColor Blue
Stop-Process -Id $ServerProcess.Id -Force

Write-Host "`n=========================================================================" -ForegroundColor Green
Write-Host "          🎉 Windows Standalone GUI Validation Complete! 🎉             " -ForegroundColor Green
Write-Host "=========================================================================" -ForegroundColor Green
Write-Host "You can inspect the visual screenshot reports here:" -ForegroundColor Green
Write-Host "    $ProjectDir\summaries\test_report\01_homepage_dashboard.png" -ForegroundColor Cyan
Write-Host "Standalone premium executable ready: dist\TubeLM.exe" -ForegroundColor Cyan
Write-Host ""
