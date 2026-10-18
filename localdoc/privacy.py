"""OS-level network denial for packaged processing, in addition to Python socket denial."""
import ctypes
from pathlib import Path
import subprocess
import sys
from .core import DocumentError
from .runtime import resource_root

_active = False

def enforce_offline():
    global _active
    if _active:
        return
    if sys.platform == 'darwin':
        library = ctypes.CDLL('/usr/lib/libsandbox.dylib')
        init = library.sandbox_init
        init.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)]
        init.restype = ctypes.c_int
        error = ctypes.c_char_p()
        result = init(b'(version 1) (allow default) (deny network*)', 0, ctypes.byref(error))
        if result != 0:
            if error.value:
                library.sandbox_free_error.argtypes = [ctypes.c_char_p]
                library.sandbox_free_error(error)
            raise DocumentError('Не удалось включить системный запрет сети macOS. Обработка заблокирована')
    elif sys.platform == 'win32' and getattr(sys, 'frozen', False):
        script = resource_root()/'verify-network.ps1'
        if not script.is_file():
            raise DocumentError('Отсутствует проверка сетевой защиты. Переустановите приложение')
        result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                                 '-File',str(script),'-Directory',str(Path(sys.executable).parent)],
                                capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode != 0:
            raise DocumentError('Сетевые правила отсутствуют или брандмауэр выключен. Обработка заблокирована. Переустановите приложение и проверьте брандмауэр Windows')
    _active = True
