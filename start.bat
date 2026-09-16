@echo off
REM ISP Accountability Monitor - Windows launcher

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment creation failed. Run manually: python -m venv venv
    pause
    exit /b 1
)

echo Starting ISP Accountability Monitor...
echo Access dashboard at http://localhost:8000
echo Press Ctrl+C to stop monitoring
echo.
echo Installing dependencies if needed...
call venv\Scripts\pip install -r requirements.txt >nul 2>&1

call venv\Scripts\activate
python src/main.py

REM Cleanup on exit (optional)
REM pause
