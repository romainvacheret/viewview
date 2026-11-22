# Built on Apple Silicon macOS using the flake's Python and native libraries.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
heif_datas, heif_binaries, heif_imports = collect_all('pillow_heif')
a = Analysis(
    [str(root / 'packaging' / 'entry.py')],
    pathex=[str(root)],
    binaries=heif_binaries,
    datas=heif_datas + [(str(root / 'viewview' / 'style.qss'), 'viewview')],
    hiddenimports=heif_imports + collect_submodules('hachoir'),
    excludes=['PySide6.QtTest'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='Viewview',
    console=False, target_arch='arm64', codesign_identity=None,
)
collection = COLLECT(exe, a.binaries, a.datas, name='Viewview')
app = BUNDLE(collection, name='Viewview.app',
             bundle_identifier='org.viewview.Viewview',
             info_plist={'CFBundleShortVersionString': '0.1.0',
                         'NSHighResolutionCapable': True})
