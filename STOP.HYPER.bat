@echo off
setlocal
cd /d C:\Users\Fiordok\Desktop\Macchinetta_IG

echo ====================================================
echo               ARRESTO HYPER (M5)
echo ====================================================
echo.

echo [1/3] Chiusura finestra Hyper M5...
taskkill /FI "WINDOWTITLE eq HYPER_GOLD_M5*" /F /T >nul 2>&1

echo [2/3] Chiusura processi sulle porte 8501 e 8502...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8501\>"') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8502\>"') do (
    taskkill /F /PID %%p >nul 2>&1
)

echo [3/3] Chiusura processi Python Hyper residui...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*hyper_gold*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo [OK] Tutti i processi Hyper sono stati chiusi!
ping 127.0.0.1 -n 3 >nul
exit
