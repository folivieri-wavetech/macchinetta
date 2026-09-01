@echo off
cd C:\Users\Fiordok\Desktop\Macchinetta_IG

echo =========================================
echo    AVVIO MACCHINETTA TREND (Locale)
echo =========================================

echo.
echo Avvio la Dashboard Trend...
:: Usiamo /c cosi la finestra si chiude da sola se muore Python
start "Dashboard Trend" cmd /c "streamlit run MACCHINETTA_TREND/Dashboard_Trend.py --server.port 8504"

echo.
echo Sistema in fase di avvio! Il browser si aprira' a breve.
exit
