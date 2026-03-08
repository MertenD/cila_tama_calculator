# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec-Datei für TAMA Calculator.

Diese Datei definiert, wie die Anwendung gepackt werden soll.
Sie kann direkt mit PyInstaller verwendet werden:
  pyinstaller TAMA_Calculator.spec
"""

import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Sammle alle Daten von Flask und SimpleITK
datas = [
    ('templates', 'templates'),
    ('calculate_tama.py', '.'),
]

# Füge tama_areas.csv hinzu, falls vorhanden
import os
if os.path.exists('tama_areas.csv'):
    datas.append(('tama_areas.csv', '.'))

# Sammle binaries und datas von SimpleITK
tmp_ret = collect_all('SimpleITK')
datas += tmp_ret[0]
binaries = tmp_ret[1]

# Sammle Flask templates
tmp_ret = collect_all('flask')
datas += tmp_ret[0]

# Hidden imports
hiddenimports = [
    'flask',
    'flask_cors',
    'SimpleITK',
    'numpy',
    'csv',
    'queue',
    'threading',
    'werkzeug',
    'jinja2',
    'click',
    'itsdangerous',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TAMA_Calculator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Zeige Konsole für Debug-Ausgaben
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Für macOS: Erstelle .app Bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='TAMA_Calculator.app',
        icon=None,
        bundle_identifier='com.tama.calculator',
    )
