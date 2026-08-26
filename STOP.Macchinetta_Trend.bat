@echo off
cd C:\Users\Fiordok\Desktop\Macchinetta_IG

echo =========================================
echo    SPEGNIMENTO MACCHINETTA TREND...
echo =========================================
echo.

:: Questo comando uccide tutti i processi python attivi per chiudere la dashboard
taskkill /F /IM python.exe /T >nul 2>&1

echo.
echo Dashboard arrestata con successo!
echo Tutte le finestre nere verranno chiuse.
timeout /t 3 >nul
