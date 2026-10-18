"""Reject a supposedly legacy bundle that embeds newer-OS Mach-O files."""
from pathlib import Path
import re
import subprocess
import sys
root = Path(sys.argv[1])
maximum = tuple(map(int,sys.argv[2].split('.')))
magic = {b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf'}
errors=[]; count=0
for path in root.rglob('*'):
    if not path.is_file() or path.is_symlink(): continue
    with path.open('rb') as f:
        if f.read(4) not in magic: continue
    count += 1
    output = subprocess.check_output(['otool','-l',str(path)],text=True)
    dependencies = subprocess.check_output(['otool','-L',str(path)],text=True)
    for line in dependencies.splitlines():
        if not line.startswith('\t'): continue
        dependency=line.strip().split(' (compatibility version',1)[0]
        if dependency.startswith('/') and not dependency.startswith(('/usr/lib/','/System/Library/')):
            errors.append(str(path.relative_to(root))+': external dependency '+dependency)
    for command in output.split('Load command '):
        if not re.search(r'cmd (LC_VERSION_MIN_MACOSX|LC_BUILD_VERSION)\s',command):continue
        match=re.search(r'^\s*(?:version|minos)\s+([0-9.]+)',command,re.M)
        if match:
            version=tuple(map(int,match.group(1).split('.')))
            if (version+(0,0,0))[:3] > (maximum+(0,0,0))[:3]:
                errors.append(str(path.relative_to(root))+': minimum '+match.group(1))
if not count: raise SystemExit('No Mach-O files found')
if errors: raise SystemExit('Legacy compatibility audit failed:\n'+'\n'.join(errors))
print(f'Mach-O minimum-OS audit passed for {count} binaries (<= {sys.argv[2]}). Old-hardware runtime testing still required.')
