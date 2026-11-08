#!/usr/bin/env python3
"""
actualizar_local.py - Regenera data/ocupacion_<CD>.json desde BigQuery y lo publica en GitHub.

Uso:
  python actualizar_local.py              # regenera y publica (si hay cambios)
  python actualizar_local.py --no-push    # solo regenera (prueba)
  python actualizar_local.py --loop 15    # repite cada 15 minutos hasta Ctrl+C

Requisitos: credenciales de gcloud (gcloud auth application-default login) y sesion de gh (gh auth login).
Si el CD o las zonas cambian, se pasan a fetch_ocupacion.py con --wh y --zones.
"""
import os, subprocess, sys, time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONWARNINGS='ignore')

def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def run(cmd):
    return subprocess.run(cmd, cwd=BASE, env=env, capture_output=True, text=True)

def once(push):
    r = run([sys.executable, 'fetch_ocupacion.py'])
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()
        log('ERROR al generar datos: ' + (tail[-1][:300] if tail else 'sin detalle'))
        return 1
    log('Datos generados')
    if not push:
        return 0
    run(['git', 'add', 'data/'])
    if run(['git', 'diff', '--staged', '--quiet']).returncode == 0:
        log('Sin cambios que publicar')
        return 0
    msg = f"data: actualizacion local {datetime.now():%Y-%m-%d %H:%M}"
    c = run(['git', 'commit', '-m', msg])
    if c.returncode != 0:
        log('ERROR commit: ' + (c.stderr or c.stdout).strip()[-300:])
        return 1
    helper = ['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential']
    pull = run([*helper, 'pull', '--rebase', '-X', 'theirs', 'origin', 'main'])
    if pull.returncode != 0:
        log('ERROR pull --rebase: ' + (pull.stderr or pull.stdout).strip()[-300:])
        return 1
    p = run([*helper, 'push', 'origin', 'main'])
    if p.returncode != 0:
        log('ERROR push: ' + (p.stderr or p.stdout).strip()[-300:])
        return 1
    log('Publicado: ' + msg)
    return 0

def main():
    push = '--no-push' not in sys.argv
    if '--loop' in sys.argv:
        i = sys.argv.index('--loop')
        minutes = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 15
        log(f'Modo repeticion cada {minutes} min. Ctrl+C para detener.')
        while True:
            try: once(push)
            except Exception as e: log(f'ERROR: {e}')
            time.sleep(minutes * 60)
    return once(push)

if __name__ == '__main__':
    sys.exit(main())
