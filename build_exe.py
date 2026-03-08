"""
Build-Skript zur Erstellung einer ausführbaren Datei für die TAMA-App.

Dieses Skript verwendet PyInstaller, um die Flask-Anwendung in eine
standalone .exe (Windows) oder .app (Mac) zu verpacken.
"""

import PyInstaller.__main__
import os
import sys
import shutil

# Bestimme das Betriebssystem
is_windows = sys.platform.startswith('win')
is_mac = sys.platform.startswith('darwin')

# Basis-Konfiguration
app_name = 'TAMA_Calculator'
icon_file = 'icon.ico' if is_windows else 'icon.icns'

# PyInstaller-Argumente
args = [
    'app.py',  # Hauptskript
    '--name=' + app_name,
    '--onefile',  # Eine einzelne ausführbare Datei
    '--windowed',  # Kein Konsolenfenster (bei Windows)
    '--clean',  # Cache vor Build leeren

    # Füge alle benötigten Dateien hinzu
    '--add-data=templates;templates',
    '--add-data=calculate_tama.py;.',
    '--add-data=tama_areas.csv;.' if os.path.exists('tama_areas.csv') else '--collect-all=flask',

    # Hidden Imports für Flask und Abhängigkeiten
    '--hidden-import=flask',
    '--hidden-import=flask_cors',
    '--hidden-import=SimpleITK',
    '--hidden-import=numpy',
    '--hidden-import=csv',
    '--hidden-import=queue',
    '--hidden-import=threading',

    # Sammle alle Flask-Pakete
    '--collect-all=flask',
    '--collect-all=flask_cors',
    '--collect-all=SimpleITK',

    # Optimierungen
    '--optimize=2',
]

# Icon hinzufügen, falls vorhanden
if os.path.exists(icon_file):
    args.append(f'--icon={icon_file}')

print("=" * 70)
print(f"Building {app_name} für {sys.platform}")
print("=" * 70)
print()

# Führe PyInstaller aus
PyInstaller.__main__.run(args)

print()
print("=" * 70)
print("Build abgeschlossen!")
print("=" * 70)
print()
print(f"Die ausführbare Datei findest du im 'dist' Ordner:")
if is_windows:
    print(f"  -> dist/{app_name}.exe")
else:
    print(f"  -> dist/{app_name}")
print()
