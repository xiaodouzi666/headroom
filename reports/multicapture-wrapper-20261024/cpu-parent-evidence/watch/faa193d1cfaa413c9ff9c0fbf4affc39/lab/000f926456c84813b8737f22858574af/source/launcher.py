import subprocess, sys
child = subprocess.call([sys.executable, 'train.py', '--batch', '8'])
raise SystemExit(child)
