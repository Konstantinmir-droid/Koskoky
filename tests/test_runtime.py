import ctypes
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from localdoc import runtime
from localdoc.macos_volume import StatFS64, is_local

class PlatformTests(unittest.TestCase):
    def test_frozen_resources_are_not_executable_directory(self):
        with patch.object(runtime.sys, 'frozen', True, create=True), patch.object(runtime.sys, '_MEIPASS', '/example/Contents/Frameworks', create=True):
            self.assertEqual(runtime.resource_root(), Path('/example/Contents/Frameworks'))
    def test_mac_data_outside_app_bundle(self):
        with patch.object(runtime.sys, 'platform', 'darwin'), patch.object(runtime.Path, 'home', return_value=Path('/Users/test')):
            self.assertEqual(runtime.state_directory(Path('/Applications/LocalDocRenamer.app/Contents/Resources')),
                             Path('/Users/test/Library/Application Support/LocalDocRenamer'))
    def test_windows_portable_data_next_to_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); (base/'portable.flag').touch()
            with patch.object(runtime.sys, 'platform', 'win32'), patch.object(runtime.sys, 'executable', str(base/'app.exe')), patch.object(runtime.sys, 'frozen', True, create=True):
                self.assertEqual(runtime.state_directory(base/'_internal'), base/'state')
    def test_native_tool_name_uses_platform(self):
        import os
        root=Path('/resources')
        self.assertEqual(runtime.native_tool(root,'tesseract').name, 'tesseract.exe' if os.name == 'nt' else 'tesseract')
    def test_darwin_local_and_remote_volume_flags(self):
        for flags, expected in [(0x1000,True),(0,False)]:
            def fake_statfs(path, result):
                ctypes.cast(result, ctypes.POINTER(StatFS64)).contents.f_flags = flags
                return 0
            self.assertEqual(is_local(Path.cwd(), SimpleNamespace(statfs64=fake_statfs)), expected)
    def test_darwin_mount_query_failure_is_closed(self):
        def fake_statfs(path, result): return -1
        with self.assertRaises(OSError): is_local(Path.cwd(), SimpleNamespace(statfs64=fake_statfs))
    def test_darwin_abi_missing_is_closed(self):
        with self.assertRaises(OSError): is_local(Path.cwd(), SimpleNamespace())
