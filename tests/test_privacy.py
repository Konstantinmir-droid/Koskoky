from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from localdoc import privacy
from localdoc.core import DocumentError

class PrivacyTests(unittest.TestCase):
    def test_guard_preserves_imports_and_denies_socket_creation(self):
        import subprocess
        import sys
        code = '''
from localdoc.engine import disable_network
from localdoc.core import DocumentError
disable_network()
import ssl, urllib.request, socket
for operation in [socket.socket, lambda: socket.create_connection(('127.0.0.1', 9)), lambda: socket.getaddrinfo('localhost', 9)]:
    try:
        operation()
    except DocumentError:
        continue
    raise SystemExit('Network guard was bypassed')
'''
        result = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_packaged_windows_missing_guard_blocks(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(privacy.sys,'platform','win32'), patch.object(privacy.sys,'frozen',True,create=True), patch.object(privacy,'_active',False), patch.object(privacy,'resource_root',return_value=Path(tmp)):
            with self.assertRaises(DocumentError): privacy.enforce_offline()
    def test_packaged_windows_inactive_rules_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'verify-network.ps1').touch()
            with patch.object(privacy.sys,'platform','win32'), patch.object(privacy.sys,'frozen',True,create=True), patch.object(privacy,'_active',False), patch.object(privacy,'resource_root',return_value=root), patch.object(privacy.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
                with self.assertRaises(DocumentError): privacy.enforce_offline()
                self.assertFalse(privacy._active)
    def test_packaged_windows_active_rules_allow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'verify-network.ps1').touch()
            with patch.object(privacy.sys,'platform','win32'), patch.object(privacy.sys,'frozen',True,create=True), patch.object(privacy,'_active',False), patch.object(privacy,'resource_root',return_value=root), patch.object(privacy.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
                privacy.enforce_offline(); self.assertTrue(privacy._active)
    def test_mac_sandbox_failure_blocks(self):
        def init(profile,flags,error):return -1
        with patch.object(privacy.sys,'platform','darwin'),patch.object(privacy,'_active',False),patch.object(privacy.ctypes,'CDLL',return_value=SimpleNamespace(sandbox_init=init)):
            with self.assertRaises(DocumentError):privacy.enforce_offline()
            self.assertFalse(privacy._active)
    def test_mac_profile_denies_network(self):
        calls=[]
        def init(profile,flags,error):calls.append(profile);return 0
        with patch.object(privacy.sys,'platform','darwin'),patch.object(privacy,'_active',False),patch.object(privacy.ctypes,'CDLL',return_value=SimpleNamespace(sandbox_init=init)):
            privacy.enforce_offline(); self.assertTrue(privacy._active)
            self.assertIn(b'(deny network*)',calls[0])
