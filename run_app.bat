@echo off
REM ------------------------------------------------------------------
REM  Daily Money Transfer Manager 2026 - Windows launcher
REM  Creates a local virtual environment on first run, installs the
REM  requirements and starts the Streamlit application.
REM ------------------------------------------------------------------
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Could not create a virtual environment. Is Python 3.11+ installed?
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if not exist ".venv\.installed" (
    echo Installing requirements...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installation failed.
        pause
        exit /b 1
    )
    echo ok> ".venv\.installed"
)

echo Starting Daily Money Transfer Manager...
echo The application opens in your browser at http://localhost:8501
python -m streamlit run app.py --server.port 8501
pause
