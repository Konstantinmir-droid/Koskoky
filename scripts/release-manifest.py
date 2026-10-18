import hashlib
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
items = {}
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'SHA256.json':
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                h.update(block)
        items[path.relative_to(root).as_posix()] = h.hexdigest()
(root/'SHA256.json').write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding='utf-8')
