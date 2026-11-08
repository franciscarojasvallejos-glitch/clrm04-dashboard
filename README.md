# Ocupación de ubicaciones · CLRM04

Tablero de ocupación de ubicaciones del CD CLRM04 (zonas RS, RK y BL). Cada ubicación se colorea por cantidad de SKUs
(vacía, 1, 2, 3, 4+). Incluye KPIs, búsqueda por ubicación o SKU, y avisos cuando los datos están viejos.

## Cómo funciona
- `fetch_ocupacion.py` consulta BigQuery (`meli-bi-data.WHOWNER`: `LK_FBM_WMS_ADDRESSES` y `BT_FBM_STOCK_3_ADDRESS`) y genera `data/ocupacion_CLRM04.json`.
- `index.html` lee ese JSON y se vuelve a cargar solo cada 60 s. Para otro CD basta cambiar `CONFIG` al inicio del archivo.
- `actualizar_local.py` ejecuta lo anterior y publica los cambios en GitHub.

## Actualizar
    python actualizar_local.py              # una vez
    python actualizar_local.py --loop 15    # cada 15 minutos

Requiere `gcloud auth application-default login` y `gh auth login`.

## Frescura de los datos
BigQuery se carga por lotes, con 1 a 1,5 h de retraso respecto del WMS. Por eso el tablero muestra tanto el último
movimiento de stock como la hora en que se generó el archivo. No es una vista en tiempo real del WMS.

## Otro CD o zonas
    python fetch_ocupacion.py --wh CLRM03 --zones RK,BL
