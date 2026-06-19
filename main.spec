# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all MNE data files including .pyi stub files
mne_datas = collect_data_files('mne', include_py_files=True)

# Collect MNE Qt Browser data files (icons, etc.)
mne_qt_browser_datas = collect_data_files('mne_qt_browser')

# Collect all MNE submodules to ensure everything is included
mne_hidden_imports = collect_submodules('mne')

# Collect mne_qt_browser submodules
mne_qt_browser_hidden_imports = collect_submodules('mne_qt_browser')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=mne_datas + mne_qt_browser_datas,
    hiddenimports=mne_hidden_imports + mne_qt_browser_hidden_imports + [
        'mne',
        'mne.io',
        'mne.viz',
        'mne.export',
        'mne_qt_browser',
        'lazy_loader',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
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
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)
