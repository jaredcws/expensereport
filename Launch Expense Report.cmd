@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=%CD%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYTHONW=%VENV_DIR%\Scripts\pythonw.exe"

if not exist "%VENV_PYTHON%" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 goto :error
)

"%VENV_PYTHON%" -c "import PySide6, PIL, reportlab, fitz, rapidocr_onnxruntime" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

echo Launching Expense Report App...
start "" "%VENV_PYTHONW%" -m expense_report_app.app
exit /b 0

:error
echo.
echo Launch failed. Press any key to close this window.
pause >nul
exit /b 1
