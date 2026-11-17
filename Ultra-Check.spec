# -*- mode: python ; coding: utf-8 -*-
import ssl
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

datas = [('assets', 'assets'), ('chrome-extension', 'chrome-extension')]
# Runtime SSL trust data required by this Python distribution.
ssl_trust = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if ssl_trust.exists(): datas.append((str(ssl_trust), '.'))
binaries = []
hiddenimports = []
datas += collect_data_files('tzdata')
binaries += collect_dynamic_libs('winrt')
hiddenimports += collect_submodules('winrt')


a = Analysis(
    ['ultra_server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Ultra-Check',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
