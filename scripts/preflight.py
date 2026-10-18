"""Fail a release build if any mandatory runtime dependency is missing."""
from pathlib import Path
import os
import struct
import platform
import sys
root = Path(__file__).resolve().parent.parent
missing = []
suffix = '.exe' if os.name == 'nt' else ''
for name in ['vendor/tesseract/tesseract' + suffix, 'vendor/tesseract/tessdata/rus.traineddata',
             'vendor/tesseract/tessdata/eng.traineddata', 'vendor/antiword/antiword' + suffix,
             'vendor/antiword/UTF-8.txt', 'vendor/licenses/CONTENTS.txt']:
    if not (root/name).is_file():
        missing.append(name)
models = list((root/'models').glob('*.gguf'))
if not models:
    missing.append('models/Qwen3-4B-or-8B.gguf')
for model in models:
    with model.open('rb') as f:
        if f.read(4) != b'GGUF':
            missing.append('Invalid GGUF: ' + model.name)
if struct.calcsize('P') != 8 or not (os.name == 'nt' or (sys.platform == 'darwin' and platform.machine() == 'x86_64')):
    missing.append('Windows x64 or macOS Intel native build environment')
if missing:
    print('Build blocked. Missing prerequisites:\n' + '\n'.join(missing))
    sys.exit(1)
print('Dependency paths checked. DLL dependencies, model compatibility and OCR require smoke testing.')
