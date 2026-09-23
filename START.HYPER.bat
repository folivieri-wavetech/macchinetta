@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d C:\Users\Fiordok\Desktop\Macchinetta_IG

echo ====================================================
echo               AVVIO HYPER (M5)
echo ====================================================
echo.

echo Avvio Hyper Gold M5 su localhost:8502...
start "HYPER_GOLD_M5" cmd /k "streamlit run hyper_gold_m1_app.py --server.port 8502"

echo.
echo [OK] Sistema Hyper M5 avviato!
echo La finestra rimarra aperta per mostrare i log in tempo reale.
echo Per fermare tutto e chiudere le finestre nere, esegui STOP.HYPER.bat.
echo.
ping 127.0.0.1 -n 4 >nul
exit
