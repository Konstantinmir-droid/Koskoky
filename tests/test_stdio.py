import os
from pathlib import Path
import subprocess
import sys
import unittest

class StdioTests(unittest.TestCase):
    def test_gui_process_can_start_with_closed_standard_descriptors(self):
        code='''
import os, sys
from localdoc.runtime import ensure_stdio
os.close(1)
os.close(2)
sys.stdout = None
sys.stderr = None
ensure_stdio()
a = os.dup(1)
b = os.dup(2)
os.close(a)
os.close(b)
assert sys.stdout is not None
assert sys.stderr is not None
'''
        env=dict(os.environ)
        env['PYTHONPATH']=str(Path(__file__).resolve().parent.parent)
        result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0)
