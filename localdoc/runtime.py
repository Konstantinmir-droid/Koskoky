"""Platform-specific bundle paths. User data is never written into a signed Mac app."""
from pathlib import Path
import os
import sys


def resource_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def state_directory(resources: Path) -> Path:
    # A Windows portable marker is next to the EXE, outside _internal.
    executable_dir = Path(sys.executable).parent
    portable_root = executable_dir if getattr(sys, 'frozen', False) else resources
    if sys.platform != 'darwin' and (portable_root / 'portable.flag').exists():
        return portable_root / 'state'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'LocalDocRenamer'
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LocalDocRenamer'


def native_tool(resources: Path, name: str) -> Path:
    suffix = '.exe' if os.name == 'nt' else ''
    return resources / 'vendor' / name / (name + suffix)


def ensure_stdio():
    # Windows GUI bootloaders may leave descriptor 1/2 invalid. llama.cpp's output
    # suppression duplicates these descriptors even with verbose=False.
    # Route them to the null device before importing the inference library.
    for descriptor in (1, 2):
        try:
            os.fstat(descriptor)
        except OSError:
            opened = os.open(os.devnull, os.O_WRONLY)
            if opened != descriptor:
                os.dup2(opened, descriptor)
                os.close(opened)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
