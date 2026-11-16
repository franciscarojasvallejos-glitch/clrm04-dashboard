# Ocupación de ubicaciones · CLRM04

Tablero de CLRM04 (zonas RS, RK y BL), con el mismo modelo del tablero de CLRM03:
- **Mapa de ocupación:** ubicaciones coloreadas por cantidad de SKUs, por zona y pasillo, con buscador lateral.
- **Inventario SKU:** SKUs con su catálogo, ubicaciones y filtros por zona.
- **Putaway:** movables pendientes con SLA, NT, búsqueda y un filtro "Sin actualizar" para registros que llevan días sin cambios.

No incluye la pestaña *Sugerencias de guardado*: sus reglas son de CLRM03 y para CLRM04 aún no están definidas.

## Cómo funciona
- Los scripts consultan BigQuery (`meli-bi-data.WHOWNER`) y generan `data/*_CLRM04.json`.
- `index.html` lee esos archivos y se recarga solo. Las zonas y pasillos se calculan desde los datos.
- `actualizar_local.py` ejecuta todo y publica los cambios en GitHub.

## Actualizar
    python actualizar_local.py              # una vez
    python actualizar_local.py --loop 15    # cada 15 minutos

Requiere `gcloud auth application-default login` y `gh auth login`.

## Visibilidad de sellers y usuarios
El tablero es público y muestra los **sellers y números de usuario reales** del putaway y el check-in. Para ocultarlos
(reemplazarlos por códigos estables `SELLER-xxxxxx` / `USR-xxxxxx` antes de publicar):

    python actualizar_local.py --anonimizar

## Otro CD o zonas
    set WAREHOUSE=CLRM03 & set ZONES=RK,BL & python actualizar_local.py --no-push

## Frescura de los datos
BigQuery se carga por lotes, con 1 a 1,5 h de retraso respecto del WMS. El plazo (SLA) del putaway es una estimación
calculada desde BigQuery: no coincide con el plazo real del WMS. No es una vista en tiempo real del WMS.
