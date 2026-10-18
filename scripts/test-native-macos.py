"""Build-only diagnostics. All inputs are synthetic; preserve native failure codes."""
import subprocess
import sys

probes = {
    'pdf_import': ['-c', 'import fitz; print(fitz.VersionBind)'],
    'qt_import': ['-c', 'from PyQt5 import QtWidgets; print("Qt imported")'],
    'qt_application': ['-c', 'from PyQt5.QtWidgets import QApplication; app=QApplication([]); print("Application created")'],
    'pdf_then_qt': ['-c', 'import fitz; from PyQt5 import QtWidgets; print("Both imported")'],
    'qt_then_pdf': ['-c', 'from PyQt5 import QtWidgets; import fitz; print("Both imported")'],
}
for name in ['test_core', 'test_gui', 'test_privacy', 'test_runtime', 'test_stdio']:
    probes[name] = ['-m', 'unittest', 'discover', '-s', 'tests', '-p', name+'.py', '-v']
probes['combined_suite'] = ['-m', 'unittest', 'discover', '-s', 'tests', '-v']
failures = []
for name, args in probes.items():
    print('\nNative probe: '+name, flush=True)
    result = subprocess.run([sys.executable, '-X', 'faulthandler', *args])
    print(f'Native probe {name}: exit {result.returncode}', flush=True)
    if result.returncode:
        failures.append((name,args))
if failures:
    name, args = failures[0]
    print('Debugger backtrace for '+name, flush=True)
    subprocess.run(['lldb','--batch','-o','settings set target.process.stop-on-exec false',
                    '-o','run','-o','thread backtrace all',
                    '--',sys.executable,*args],timeout=120)
    raise SystemExit('Native probes failed: '+', '.join(name for name,_ in failures))
