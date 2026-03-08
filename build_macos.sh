#!/bin/bash
# Build-Skript für macOS

echo "======================================================================"
echo "TAMA Calculator - macOS Build"
echo "======================================================================"
echo ""

# Prüfe ob PyInstaller installiert ist
python3 -c "import PyInstaller" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "PyInstaller ist nicht installiert. Installiere es jetzt..."
    pip3 install pyinstaller
fi

echo "Starte Build-Prozess..."
echo ""

# Führe PyInstaller mit der Spec-Datei aus
pyinstaller --clean TAMA_Calculator.spec

echo ""
echo "======================================================================"
echo "Build abgeschlossen!"
echo "======================================================================"
echo ""
echo "Die ausführbare Datei findest du hier:"
echo "  dist/TAMA_Calculator.app"
echo ""
echo "Du kannst die .app Datei nun auf jedem Mac ausführen,"
echo "ohne Python installieren zu müssen."
echo ""
