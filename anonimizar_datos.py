#!/usr/bin/env python3
"""
anonimizar_datos.py - Reemplaza sellers y numeros de usuario por codigos antes de publicar los datos.

El sitio es publico: los nombres de sellers y los usuarios del WMS no deben quedar a la vista. Cada valor se cambia por
un codigo estable (SELLER-A1B2C3 / USR-D4E5F6) calculado con una sal secreta que vive SOLO en tu equipo
(~/.clrm04_salt, nunca en el repositorio). El mismo seller siempre recibe el mismo codigo, asi que la busqueda y el
agrupado siguen funcionando, pero el nombre real no se puede recuperar desde los archivos publicados.

Despues de transformar, verifica que ningun valor original quede en NINGUN archivo de data/. Si queda alguno, termina con
error (codigo 1) y actualizar_local.py no publica nada.
"""
import hashlib, json, os, re, secrets, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
WH = os.environ.get('WAREHOUSE', 'CLRM04')
SALT_FILE = os.path.join(os.path.expanduser('~'), '.clrm04_salt')

# archivo -> (lista de registros, {campo: prefijo del codigo})
TARGETS = {
    f'putaway_{WH}.json': ('movables', {'seller': 'SELLER', 'usuario': 'USR'}),
    f'checkin_{WH}.json': ('items', {'seller': 'SELLER', 'chk_user': 'USR', 'pw_user': 'USR'}),
}
# Etiquetas del sistema que no identifican a nadie: se dejan tal cual para no perder el significado.
SYSTEM_LABELS = {'INBOUND_TRANSFER'}
CODED = re.compile(r'^(SELLER|USR)-[0-9A-F]{6}$')

def get_salt():
    if not os.path.exists(SALT_FILE):
        with open(SALT_FILE, 'w', encoding='utf-8') as f:
            f.write(secrets.token_hex(16))
    return open(SALT_FILE, encoding='utf-8').read().strip()

def code(salt, prefix, value):
    return f"{prefix}-{hashlib.sha256((salt + '|' + prefix + '|' + str(value)).encode('utf-8')).hexdigest()[:6].upper()}"

def main():
    salt = get_salt()
    originals = set()
    stats = {}
    for fname, (key, fields) in TARGETS.items():
        path = os.path.join(DATA, fname)
        if not os.path.exists(path):
            print(f"  (omitido, no existe) {fname}")
            continue
        with open(path, encoding='utf-8') as f:
            doc = json.load(f)
        n = 0
        for rec in doc.get(key, []):
            for field, prefix in fields.items():
                v = rec.get(field)
                if v in (None, '') or CODED.match(str(v)) or str(v) in SYSTEM_LABELS:
                    continue
                originals.add(str(v))
                rec[field] = code(salt, prefix, v)
                n += 1
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, separators=(',', ':'), ensure_ascii=False)
        stats[fname] = n
        print(f"  {fname}: {n} valores reemplazados")

    # Verificacion: ningun valor original puede quedar en ningun archivo de data/
    leaks = []
    for fn in sorted(os.listdir(DATA)):
        if not fn.endswith('.json'):
            continue
        # El catalogo trae marcas y titulos publicos del marketplace; una marca puede coincidir con el nombre de un
        # seller (ej. una marca llamada igual que su vendedor) sin revelar quien guardo que. No se revisa.
        if fn.startswith('catalog_'):
            continue
        text = open(os.path.join(DATA, fn), encoding='utf-8', errors='ignore').read()
        for v in originals:
            if len(v) >= 4 and f'"{v}"' in text:
                leaks.append((fn, v))
    if leaks:
        print(f"ERROR: quedaron {len(leaks)} valores originales en los archivos (ej: {leaks[:3]})")
        return 1
    print(f"  Verificado: {len(originals)} valores originales distintos, ninguno queda en data/")
    return 0

if __name__ == '__main__':
    sys.exit(main())
