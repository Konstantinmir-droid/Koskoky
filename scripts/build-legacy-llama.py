"""Build llama.cpp for High Sierra, removing upstream forced Metal and new libc++ fs.
Build-time only; public upstream sources. No document processing or runtime downloads.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import subprocess
import sys
import tarfile
import urllib.request

if sys.platform != 'darwin' or platform.machine() != 'x86_64':
    raise SystemExit('Requires Intel macOS builder')
root = Path(__file__).resolve().parent.parent
work = root/'.legacy-llama'
work.mkdir(exist_ok=True)
meta = json.load(urllib.request.urlopen('https://pypi.org/pypi/llama-cpp-python/0.3.16/json', timeout=60))
asset = next(x for x in meta['urls'] if x['packagetype'] == 'sdist')
raw = urllib.request.urlopen(asset['url'], timeout=120).read()
if hashlib.sha256(raw).hexdigest() != asset['digests']['sha256']:
    raise SystemExit('Upstream source digest mismatch')
archive = work/'source.tar.gz'
archive.write_bytes(raw)
with tarfile.open(archive) as tar:
    members=[]
    for member in tar.getmembers():
        dest=(work/member.name).resolve()
        if not dest.is_relative_to(work.resolve()):
            raise SystemExit('Unsafe archive member')
        if member.isfile() or member.isdir(): members.append(member)
    tar.extractall(work, members=members)
source=work/'llama_cpp_python-0.3.16'
cmake=source/'CMakeLists.txt'
text=cmake.read_text()
needle='set(GGML_METAL "ON" CACHE BOOL "ggml: enable Metal" FORCE)'
if needle not in text: raise SystemExit('Upstream Metal override changed')
text=text.replace(needle,'set(GGML_METAL "OFF" CACHE BOOL "ggml: enable Metal" FORCE)')
text=text.replace('set(LLAMA_BUILD_COMMON ON CACHE BOOL "Build llama.cpp common library" FORCE)',
                  'set(LLAMA_BUILD_COMMON OFF CACHE BOOL "Build llama.cpp common library" FORCE)')
cmake.write_text(text)
backend=source/'vendor/llama.cpp/ggml/src/ggml-backend-reg.cpp'
text=backend.read_text()
if '#include <filesystem>' not in text or 'std::filesystem' not in text:
    raise SystemExit('Upstream filesystem implementation changed')
backend.write_text(text.replace('#include <filesystem>','#include "legacy-filesystem.hpp"')
                       .replace('std::filesystem','ghc::filesystem'))
url='https://raw.githubusercontent.com/gulrak/filesystem/v1.5.14/include/ghc/filesystem.hpp'
header=urllib.request.urlopen(url,timeout=60).read()
(source/'vendor/llama.cpp/ggml/src/legacy-filesystem.hpp').write_bytes(header)
licenses=root/'vendor/licenses'
licenses.mkdir(parents=True,exist_ok=True)
(licenses/'ghc-filesystem-LICENSE.txt').write_bytes(urllib.request.urlopen(
    'https://raw.githubusercontent.com/gulrak/filesystem/v1.5.14/LICENSE',timeout=60).read())
(licenses/'legacy-llama-patch.json').write_text(json.dumps({
    'upstream_version':'0.3.16','upstream_sha256':asset['digests']['sha256'],
    'compat_header':url,'compat_header_sha256':hashlib.sha256(header).hexdigest(),
    'changes':['Disable forced Metal and unused common library',
               'Use ghc::filesystem instead of macOS 10.15 libc++ filesystem in backend registry'],
},indent=2))
env=dict(os.environ)
env['MACOSX_DEPLOYMENT_TARGET']='10.13'
env['CMAKE_ARGS']=env.get('CMAKE_ARGS','')+' -DLLAVA_BUILD=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF'
subprocess.run([sys.executable,'-m','pip','install',str(source),'--no-cache-dir'],check=True,env=env)
print('Legacy llama build installed; final Mach-O and runtime audits still required.')
