"""BUILD-TIME ONLY. No imports from this script are made by the installed app.
Download public model/engine data; never takes document paths as input.
"""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / 'vendor'
LICENSES = VENDOR / 'licenses'
LICENSES.mkdir(parents=True, exist_ok=True)
provenance = []


def download(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, target.open('wb') as stream:
        shutil.copyfileobj(response, stream)
    provenance.append({'url':url, 'file':target.relative_to(ROOT).as_posix(),
                       'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


if os.name == 'nt':
    # The CI environment installs conda-forge Tesseract, including its dependent DLLs.
    prefix = Path(os.environ['CONDA_PREFIX'])
    binary = prefix / 'Library' / 'bin' / 'tesseract.exe'
    if not binary.is_file():
        raise RuntimeError('conda-forge Tesseract not found at ' + str(binary))
    copy(binary, VENDOR/'tesseract/tesseract.exe')
    for dll in binary.parent.glob('*.dll'):
        copy(dll, VENDOR/'tesseract'/dll.name)
    archive = ROOT/'antiword-build.zip'
    download('https://cran.r-project.org/bin/windows/contrib/4.5/antiword_1.3.5.zip', archive)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.filename == 'antiword/bin/antiword.exe':
                target = VENDOR/'antiword/antiword.exe'
            elif info.filename.startswith('antiword/share/antiword/') and not info.is_dir():
                target = VENDOR/'antiword'/Path(info.filename).name
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    archive.unlink()
    # Preserve conda metadata and available native package license files.
    for file in (prefix/'conda-meta').glob('*.json'):
        copy(file, LICENSES/'conda-metadata'/file.name)
    for parent in (prefix/'Library/share/licenses', prefix/'info/licenses'):
        if parent.is_dir():
            shutil.copytree(parent, LICENSES/'native-licenses'/parent.name, dirs_exist_ok=True)
elif sys.platform == 'darwin' and os.environ.get('LOCALDOC_LEGACY_MAC') == '1':
    for tool in ('tesseract','antiword'):
        if not (VENDOR/tool/tool).is_file():
            raise RuntimeError('Build legacy native tools before preparing assets')
elif sys.platform == 'darwin':
    if os.uname().machine != 'x86_64':
        raise RuntimeError('Intel x86_64 build required')
    # Homebrew exists only on the build machine; PyInstaller gathers Mach-O dependencies.
    for tool in ('tesseract','antiword'):
        prefix = Path(subprocess.check_output(['brew','--prefix',tool],text=True).strip())
        copy(prefix/'bin'/tool, VENDOR/tool/tool)
        if tool == 'antiword':
            shutil.copytree(prefix/'share/antiword', VENDOR/'antiword', dirs_exist_ok=True)
        for license_file in prefix.rglob('*'):
            if license_file.is_file() and license_file.name.lower() in ('license','copying','copyright'):
                copy(license_file, LICENSES/tool/license_file.relative_to(prefix))
else:
    raise RuntimeError('Native Windows or Intel macOS builder required')

# Languages downloaded from the upstream Tesseract project, never at application runtime.
for language in ('rus', 'eng'):
    download('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/' + language + '.traineddata',
             VENDOR/'tesseract/tessdata'/(language+'.traineddata'))
for name,url in {
    'Tesseract-LICENSE.txt':'https://raw.githubusercontent.com/tesseract-ocr/tesseract/main/LICENSE',
    'Tessdata-LICENSE.txt':'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/LICENSE',
    'antiword-source.tar.gz':'https://cran.r-project.org/src/contrib/antiword_1.3.5.tar.gz',
}.items():
    download(url, LICENSES/name)

from huggingface_hub import HfApi, hf_hub_download
repo = 'Qwen/Qwen3-4B-GGUF'
revision = HfApi().model_info(repo).sha
for name in ('Qwen3-4B-Q4_K_M.gguf', 'LICENSE'):
    source = Path(hf_hub_download(repo, filename=name, revision=revision))
    target = ROOT/'models'/name if name.endswith('.gguf') else LICENSES/'Qwen3-LICENSE.txt'
    copy(source, target)
    h = hashlib.sha256()
    with target.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''):
            h.update(part)
    provenance.append({'repository':repo,'revision':revision,'file':target.relative_to(ROOT).as_posix(),'sha256':h.hexdigest()})
(ROOT/'asset-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
(LICENSES/'CONTENTS.txt').write_text('Build-time assets and provenance: asset-provenance.json.\n'
    'Inspect all native dependency licenses and source obligations before release.\n',encoding='utf-8')
print('Public build assets staged. No document has been read or uploaded.')
