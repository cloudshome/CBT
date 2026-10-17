@echo off
title Crypto Brain Terminal Launcher
echo ============================================================
echo   CRYPTO BRAIN TERMINAL (CBT / SKY) - INSTITUTIONAL DESK
echo ============================================================
echo [1/2] Launching Python FastAPI Backend Engine on Port 8000...
start "SKY Backend Engine (Port 8000)" cmd /k ".venv\Scripts\python app.py"

echo [2/2] Waiting 3 seconds for backend initialization...
timeout /t 3 /nobreak >nul

echo [3/3] Launching Vite Frontend Terminal on Port 5173...
start "SKY Frontend Terminal (Port 5173)" cmd /k "npm run frontend:dev"

echo.
echo ============================================================
echo  All systems active!
echo  Open your browser at: http://localhost:5173
echo ============================================================
pause
