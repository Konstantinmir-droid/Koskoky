# PyInstaller native build specification. Run on Windows x64 or Intel macOS.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all
root = Path(SPECPATH)
datas, binaries, hiddenimports = [], [], []
for module in ['llama_cpp', 'jsonschema']:
    d, b, h = collect_all(module)
    datas += d; binaries += b; hiddenimports += h
for folder in ['vendor', 'models']:
    for path in sorted((root/folder).rglob('*')):
        if not path.is_file():
            continue
        dest = path.parent.relative_to(root).as_posix()
        is_native = path.suffix.lower() in ('.exe','.dll','.dylib','.so') or path.name in ('tesseract','antiword')
        (binaries if is_native else datas).append((str(path), dest))
for name in ['README_RU.md', 'THIRD_PARTY_NOTICES.md', 'schema.json', 'asset-provenance.json']:
    if (root/name).is_file():
        datas.append((str(root/name), '.'))
a = Analysis([str(root/'main.py')], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='LocalDocRenamer', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          target_arch='x86_64' if sys.platform == 'darwin' else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='LocalDocRenamer')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='LocalDocRenamer.app', bundle_identifier='local.localdocrenamer.desktop',
                 info_plist={'CFBundleShortVersionString':'0.1.0',
                             'CFBundleVersion':'1',
                             'NSHighResolutionCapable':True,
                             'LSMinimumSystemVersion':'10.13' if __import__('os').environ.get('LOCALDOC_LEGACY_MAC') == '1' else '13.0'})
