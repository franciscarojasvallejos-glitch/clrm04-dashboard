#!/usr/bin/env python3
"""
fetch_ocupacion.py - Ocupacion de ubicaciones de un centro de distribucion (por defecto CLRM04, zonas RS/RK/BL).
Genera data/ocupacion_<CD>.json con un formato compacto:

  zones -> <zona> -> aisles -> <pasillo> -> <bay> -> [[nivel, posicion, n_skus, unidades, "SKU1,SKU2,...", "ID-UBICACION"], ...]

Uso:
  python fetch_ocupacion.py                       # CLRM04, zonas RS,RK,BL
  python fetch_ocupacion.py --wh CLRM03           # otro CD
  python fetch_ocupacion.py --zones RS,RK         # otras zonas
  python fetch_ocupacion.py --watch 120           # refresca cada 120 s
Requiere credenciales de gcloud (gcloud auth application-default login).
"""
import json, os, sys, time, warnings
from datetime import datetime
from zoneinfo import ZoneInfo
warnings.filterwarnings('ignore')

# Carpeta opcional con google-cloud-bigquery y dependencias (variable CLRM_LIBS) para entornos sin esos paquetes.
_libs = os.environ.get('CLRM_LIBS') or os.path.join(os.path.expanduser('~'), 'clrm03-ocupacion-py', 'libs')
if os.path.isdir(_libs):
    sys.path.insert(0, _libs)
from google.cloud import bigquery

PROJECT = 'meli-bi-data'
TZ = ZoneInfo('America/Santiago')
MAX_SKUS_PER_SLOT = 8   # SKUs que se guardan por ubicacion (el conteo n_skus es siempre el real)

SQL = f"""
WITH s AS (
  SELECT ADDRESS_ID,
         SPLIT(ADDRESS_ID, '-')[OFFSET(0)] AS zona,
         CAST(ADRS_AISLE AS INT64) AS aisle, CAST(ADRS_BAY AS INT64) AS bay,
         CAST(ADRS_LEVEL AS INT64) AS lvl, CAST(ADRS_POSITION AS INT64) AS pos
  FROM `{PROJECT}.WHOWNER.LK_FBM_WMS_ADDRESSES`
  WHERE WAREHOUSE_ID = @wh AND LOWER(ADRS_STATUS) = 'available'
    AND SPLIT(ADDRESS_ID, '-')[OFFSET(0)] IN UNNEST(@zones)),
k AS (
  SELECT ADDRESS_ID,
         COUNT(DISTINCT INVENTORY_ID) AS n, SUM(FBM_QUANTITY) AS qty,
         ARRAY_AGG(INVENTORY_ID ORDER BY FBM_QUANTITY DESC LIMIT {MAX_SKUS_PER_SLOT}) AS skus
  FROM `{PROJECT}.WHOWNER.BT_FBM_STOCK_3_ADDRESS`
  WHERE WAREHOUSE_ID = @wh AND FBM_STOCK_STATUS = 'ok'
    AND SPLIT(ADDRESS_ID, '-')[OFFSET(0)] IN UNNEST(@zones)
  GROUP BY ADDRESS_ID)
SELECT s.ADDRESS_ID AS id, s.zona, s.aisle, s.bay, s.lvl, s.pos, IFNULL(k.n, 0) AS n, IFNULL(k.qty, 0) AS qty, k.skus AS skus
FROM s LEFT JOIN k USING (ADDRESS_ID)
ORDER BY s.zona, s.aisle, s.bay, s.lvl, s.pos
"""

SQL_CUT = f"""
SELECT FORMAT_DATETIME('%Y-%m-%d %H:%M:%S', MAX(FBM_LAST_UPDATED)) AS cut
FROM `{PROJECT}.WHOWNER.BT_FBM_STOCK_3_ADDRESS` WHERE WAREHOUSE_ID = @wh
"""

def fetch(wh, zones):
    client = bigquery.Client(project=PROJECT)
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter('wh', 'STRING', wh),
        bigquery.ArrayQueryParameter('zones', 'STRING', zones)])
    print(f"  Consultando {wh} ({', '.join(zones)})...", end=' ', flush=True)
    rows = list(client.query(SQL, job_config=cfg).result())
    print(f"{len(rows):,} ubicaciones")
    if not rows:
        raise SystemExit(f"Sin ubicaciones para {wh} en las zonas {zones}: revisa el CD y las zonas.")

    data = {}
    for r in rows:
        z = data.setdefault(r.zona, {'aisles': {}})
        bay = z['aisles'].setdefault(str(r.aisle), {}).setdefault(str(r.bay), [])
        bay.append([r.lvl, r.pos, int(r.n), int(r.qty or 0), ','.join(r.skus or []), r.id])

    cut_cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('wh', 'STRING', wh)])
    cut = list(client.query(SQL_CUT, job_config=cut_cfg).result())
    stock_cut = cut[0].cut if cut else None

    stats = {}
    for zona, z in data.items():
        n_slots = occ = multi = 0
        dist = [0, 0, 0, 0]
        for aisle in z['aisles'].values():
            for slots in aisle.values():
                for _lvl, _pos, n, _qty, _skus, _id in slots:
                    n_slots += 1
                    if n > 0: occ += 1
                    if n > 1: multi += 1
                    if n >= 1: dist[min(n, 4) - 1] += 1
        stats[zona] = {'slots': n_slots, 'occ': occ, 'multi': multi, 'n1': dist[0], 'n2': dist[1], 'n3': dist[2], 'n4p': dist[3],
                       'aisles': len(z['aisles'])}
    now = datetime.now(tz=TZ)
    # 'updated' = cuando corrio este script; 'stock_cut' = ultimo cambio de stock presente en BigQuery (el dato real).
    return {'wh': wh, 'date': now.strftime('%Y-%m-%d'), 'updated': now.strftime('%H:%M:%S'),
            'stock_cut': stock_cut, 'stats': stats, 'zones': data}

def save(data):
    os.makedirs('data', exist_ok=True)
    path = f"data/ocupacion_{data['wh']}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
    tot = sum(s['slots'] for s in data['stats'].values())
    occ = sum(s['occ'] for s in data['stats'].values())
    print(f"  Guardado: {path}  ({tot:,} ubicaciones, {occ:,} con stock, {os.path.getsize(path)/1024:.0f} KB)")
    for z, s in data['stats'].items():
        print(f"    {z}: {s['slots']:,} ubic. · {s['occ']:,} ocupadas ({s['occ']/s['slots']*100:.1f} %) · {s['aisles']} pasillos")

def arg(args, name, default):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default

def main():
    args = sys.argv[1:]
    wh = arg(args, '--wh', 'CLRM04').upper()
    zones = [z.strip().upper() for z in arg(args, '--zones', 'RS,RK,BL').split(',') if z.strip()]
    if '--watch' in args:
        interval = int(arg(args, '--watch', '120'))
        print(f"Modo watch cada {interval}s. Ctrl+C para detener.")
        while True:
            try: save(fetch(wh, zones))
            except Exception as e: print(f"  ERROR: {e}")
            time.sleep(interval)
    else:
        save(fetch(wh, zones))

if __name__ == '__main__':
    main()
