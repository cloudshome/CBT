# PowerShell Launcher for Crypto Brain Terminal
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CRYPTO BRAIN TERMINAL (CBT / SKY) - INSTITUTIONAL DESK" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Write-Host "`n[1/2] Starting Python FastAPI Engine on Port 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; .venv\Scripts\python app.py"

Start-Sleep -Seconds 3

Write-Host "[2/2] Starting Vite Frontend on Port 5173..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; npm run frontend:dev"

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " Both servers launched in separate windows!" -ForegroundColor Green
Write-Host " Open your browser at: http://localhost:5173" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
