@echo off
pause
echo.
echo ohne Python installieren zu müssen.
echo Du kannst die .exe Datei nun auf jedem Windows-PC ausführen,
echo.
echo   dist\TAMA_Calculator.exe
echo Die ausführbare Datei findest du hier:
echo.
echo ======================================================================
echo Build abgeschlossen!
echo ======================================================================
echo.

pyinstaller --clean TAMA_Calculator.spec
REM Führe PyInstaller mit der Spec-Datei aus

echo.
echo Starte Build-Prozess...

)
    pip install pyinstaller
    echo PyInstaller ist nicht installiert. Installiere es jetzt...
if errorlevel 1 (
python -c "import PyInstaller" 2>nul
REM Prüfe ob PyInstaller installiert ist

echo.
echo ======================================================================
echo TAMA Calculator - Windows Build
echo ======================================================================
REM Build-Skript für Windows
