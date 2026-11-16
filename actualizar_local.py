#!/usr/bin/env python3
"""
actualizar_local.py - Regenera los JSON del dashboard de CLRM04 desde BigQuery y los publica en GitHub.

Uso:
  python actualizar_local.py              # regenera y publica (si hay cambios)
  python actualizar_local.py --no-push    # solo regenera (prueba)
  python actualizar_local.py --loop 15    # repite cada 15 minutos hasta Ctrl+C
  python actualizar_local.py --anonimizar # reemplaza sellers y usuarios por codigos antes de publicar (opcional)

Requisitos: credenciales de gcloud (gcloud auth application-default login) y sesion de gh (gh auth login).
El CD y las zonas se controlan con las variables WAREHOUSE y ZONES (por defecto CLRM04 y RS,RK,BL).
"""
import os, subprocess, sys, time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
WH = os.environ.get("WAREHOUSE", "CLRM04")
CATALOG_MAX_AGE_H = 20     # el catalogo cambia poco: una vez al dia alcanza

# Carpeta opcional con google-cloud-bigquery y dependencias (variable CLRM_LIBS), para equipos donde el
# Python del terminal no las tiene instaladas.
LIBS = os.environ.get("CLRM_LIBS") or os.path.join(os.path.expanduser("~"), "clrm03-ocupacion-py", "libs")

env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONWARNINGS="ignore", WAREHOUSE=WH)
if os.path.isdir(LIBS):
    env["PYTHONPATH"] = LIBS + os.pathsep + env.get("PYTHONPATH", "")

STEPS = [
    ["fetch_ocupacion.py"],
    ["generar_putaway_json.py"],
    ["generar_checkin_json.py", "--dias", "3"],
    ["generar_inbound_nt_json.py"],
]
CATALOG_STEP = ["generar_catalog_json.py"]
CATALOG_FILE = os.path.join(DATA, f"catalog_{WH}.json")

def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def run(cmd):
    return subprocess.run(cmd, cwd=BASE, env=env, capture_output=True, text=True)

def generate(step):
    t = time.time()
    r = run([sys.executable, *step])
    ok = r.returncode == 0
    log(f"{'OK   ' if ok else 'ERROR'} {' '.join(step)} ({time.time() - t:.0f}s)")
    if not ok:
        tail = (r.stderr or r.stdout).strip().splitlines()
        log("  " + (tail[-1][:300] if tail else "sin detalle"))
    return ok

def catalog_is_old():
    return (not os.path.exists(CATALOG_FILE)) or (time.time() - os.path.getmtime(CATALOG_FILE)) / 3600 > CATALOG_MAX_AGE_H

def once(push):
    steps = list(STEPS) + ([CATALOG_STEP] if catalog_is_old() else [])
    if not all([generate(s) for s in steps]):
        log("Fallo algun paso: no se publica nada")
        return 1
    # Decision vigente (nov-2026): el tablero publica sellers y numeros de usuario REALES, visibles para cualquiera con el
    # link. Para volver a ocultarlos, ejecutar con --anonimizar: reemplaza sellers y usuarios por codigos antes de publicar y,
    # si algo falla, no publica nada.
    if "--anonimizar" in sys.argv:
        a = run([sys.executable, "anonimizar_datos.py"])
        for line in (a.stdout or "").strip().splitlines():
            log(line.strip())
        if a.returncode != 0:
            log("ERROR al anonimizar: no se publica nada")
            return 1
    else:
        log("Datos publicados SIN anonimizar (sellers y usuarios reales). Usa --anonimizar para ocultarlos.")
    if not push:
        return 0
    run(["git", "add", "data/"])
    if run(["git", "diff", "--staged", "--quiet"]).returncode == 0:
        log("Sin cambios que publicar")
        return 0
    msg = f"data: actualizacion local {datetime.now():%Y-%m-%d %H:%M}"
    c = run(["git", "commit", "-m", msg])
    if c.returncode != 0:
        log("ERROR commit: " + (c.stderr or c.stdout).strip()[-300:])
        return 1
    helper = ["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
    p = run([*helper, "pull", "--rebase", "-X", "theirs", "origin", "main"])
    if p.returncode != 0:
        log("ERROR pull --rebase: " + (p.stderr or p.stdout).strip()[-300:])
        return 1
    pu = run([*helper, "push", "origin", "main"])
    if pu.returncode != 0:
        log("ERROR push: " + (pu.stderr or pu.stdout).strip()[-300:])
        return 1
    log("Publicado: " + msg)
    return 0

def main():
    push = "--no-push" not in sys.argv
    if "--loop" in sys.argv:
        i = sys.argv.index("--loop")
        minutes = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 15
        log(f"Modo repeticion cada {minutes} min. Ctrl+C para detener.")
        while True:
            try: once(push)
            except Exception as e: log(f"ERROR: {e}")
            time.sleep(minutes * 60)
    return once(push)

if __name__ == "__main__":
    sys.exit(main())
