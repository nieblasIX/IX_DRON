# IX DRON — Arquitectura

## 1. Principio rector

El sistema no es un dashboard: es una base de datos temporal de observaciones
(`flights[]`) con una capa de renderizado estática y desechable encima. Cada
decisión de este documento protege esa separación.

```
PARCELA → VUELO → PRODUCTOS FOTOGRAMÉTRICOS → ÍNDICES → ESTADÍSTICAS
        → COMPARACIÓN → SERIE TEMPORAL → REGLAS → RECOMENDACIONES
        → ASSETS WEB → DASHBOARD ESTÁTICO
```

## 2. Entidades conceptuales

Ya definidas hoy como dataclasses en `ixdron/models/schemas.py`, con los
mismos nombres de campo que tendrían las tablas de una futura base PostGIS:

```
CLIENT → PROJECT → PARCEL → FLIGHT → RASTER → INDEX → STATISTIC
       → CHANGE_DETECTION → REPORT → RECOMMENDATION → OBSERVATION
```

La migración futura a PostgreSQL/PostGIS es, por diseño, un mapeo directo
(`INSERT ... SELECT` desde los JSON), no una reescritura.

## 3. Estructura de directorios

```
IXDRON/
├── ixdron/                      # paquete Python (el "cerebro")
│   ├── config.py                # rutas, versión de pipeline, umbrales por defecto
│   ├── cli.py                   # ixdron process | build | list
│   ├── models/schemas.py        # entidades conceptuales (dataclasses)
│   └── pipeline/
│       ├── ingestion.py         # descubre vuelos, localiza producto ODM
│       ├── validation.py        # nunca genera un resultado falso
│       ├── raster_utils.py      # carga, recorte, remuestreo, previews web
│       ├── indices.py           # registro sensor→índice (VARI/ExG/GLI, NDVI futuro)
│       ├── statistics.py        # estadísticas por vuelo
│       ├── change_detection.py  # comparación vuelo actual vs. anterior válido
│       ├── temporal.py          # agregaciones derivadas (nunca 2026.json/2027.json)
│       ├── rules.py             # motor de reglas: observación/interpretación/recomendación
│       ├── orchestrator.py      # orquesta un vuelo o una parcela completa
│       └── web_assets.py        # único módulo que escribe en web/dashboard/data
│
├── data/                        # PRIVADO — no publicar tal cual en un repo público
│   └── clientes/{CLIENTE_ID}/parcelas/{PARCELA_ID}/
│       ├── parcel_config.json       # sensor, umbrales, nombre, caso de uso
│       ├── parcel_boundary.geojson  # geometría persistente de la parcela
│       ├── flights/{FECHA_ISO}/
│       │   ├── metadata.json        # ID, fecha, GSD, cámara, CRS, estado...
│       │   ├── odm/products/*.tif   # salida de WebODM (o products/ si es manual)
│       │   └── analysis/            # vari.tif, previews PNG, stats.json
│       └── history/flights_index.json   # flights[] — la fuente de verdad temporal
│
├── web/dashboard/               # PÚBLICO — esto es lo que se sube a GitHub Pages
│   ├── index.html
│   ├── assets/{css,js,vendor}/  # Leaflet y Plotly vendorizados (sin depender de CDN)
│   └── data/{CLIENTE}/{PARCELA}/dashboard.json + previews/*.png (generado, no editar)
│
├── scripts/generate_demo_data.py
├── docs/{ARCHITECTURE,INSTALL,USAGE}.md
└── requirements.txt
```

**Por qué esta separación PUBLIC/PRIVATE (punto 30 del prompt):** `data/`
contiene imágenes y metadata que pueden ser sensibles (ubicación exacta,
nombre del cliente). Solo `web/dashboard/` se publica. En producción,
`data/` debería vivir en un repositorio privado o almacenamiento no público;
`web/dashboard/` en el repositorio público con GitHub Pages.

### 3.1. Desacople entre datos crudos de ODM y árbol de análisis

`data/clientes/.../flights/{fecha}/` **no tiene por qué contener** el
ortomosaico ni las imágenes originales. `pipeline/odm_source.py` permite
apuntar una parcela directamente a la carpeta donde ODM/WebODM ya dejó sus
resultados (`parcel_config.json → raw_flights_root`), sin copiar nada: cada
`flights/{fecha}/` solo guarda un `source.json` (ruta absoluta al proyecto
ODM real) y los productos livianos que genera IX DRON (`vari.tif`,
previews, `stats.json`). Esto evita duplicar decenas de GB de imágenes y
mantiene el árbol de datos de IX DRON manejable en disco y en git,
independientemente de cuánto pese la carpeta de trabajo de ODM. Ver
`docs/USAGE.md → "Conectar vuelos reales de ODM/WebODM"` para el flujo
operativo completo.

## 4. Modelo de datos: por qué `flights[]` y no `2026.json`

La fecha es un atributo de cada observación, no de la estructura de archivos.
`history/flights_index.json` es una lista plana que crece indefinidamente:

```json
[
  {"flight_id": "2026-08-01", "date": "2026-08-01", "status": "baseline", "vari_mean": 0.304, "change": null, ...},
  {"flight_id": "2026-08-15", "date": "2026-08-15", "status": "processed", "vari_mean": 0.280, "change": {...}, ...}
]
```

Todas las vistas temporales (semana/mes/trimestre/año/histórico,
comparación interanual) se **derivan en memoria** a partir de esta lista
(`ixdron/pipeline/temporal.py`). Nunca se escribe una estructura por año.
Esto es lo que permite que el sistema funcione igual con 2 vuelos que con
500, y que dos, seis o cien parcelas convivan sin cambios de lógica.

## 5. Riesgos identificados y mitigación

| Riesgo | Mitigación implementada |
|---|---|
| Servir un GeoTIFF de cientos de MB en el navegador | El GeoTIFF master nunca se sirve directamente; se generan previews PNG livianos (`raster_utils.array_to_web_png`, tamaño máximo configurable). El hook para COG/PMTiles está previsto en `config.DEFAULT_COG_SIZE_THRESHOLD_MB` para cuando el volumen lo justifique. |
| Cadena de comparación rota por un vuelo fallido | Cada vuelo tiene `status` (`baseline/processed/failed`). `find_previous_valid_flight` ignora vuelos `failed` al buscar el anterior. |
| Comparar rasters no comparables (distinto CRS/resolución/sin solapamiento) | `validation.check_comparability` corre antes de cualquier resta de rasters; si falla, se registra el motivo y no se inventa un resultado. |
| Umbrales de cambio arbitrarios | Viven en `parcel_config.json` (`change_thresholds`), con default documentado en `config.py`, visibles en modo técnico. |
| Sobreingeniería prematura (PostGIS, auth, multi-tenant real) | El MVP usa JSON planos, pero con los mismos nombres de campo que las futuras tablas — la migración es un mapeo, no una reescritura. |
| Mezclar observación/interpretación/recomendación | El motor de reglas (`rules.py`) emite los tres campos por separado; la plantilla del dashboard los renderiza en bloques visualmente distintos. |
| Dependencia de CDNs externos para el dashboard | Leaflet y Plotly están vendorizados en `web/dashboard/assets/vendor/` — el sitio funciona sin conexión a servicios de terceros. |

## 6. Ruta de escalamiento (madurez de datos)

La interfaz evoluciona automáticamente según cuántos vuelos existen
(`temporal.data_maturity_level`), sin ninguna intervención manual:

| N° de vuelos | Nivel | Qué se activa |
|---|---|---|
| 1 | `baseline` | "Vuelo de referencia" |
| 2 | `comparison` | ΔVARI, mapa de cambio, recomendaciones |
| 3+ | `timeseries` | Gráfica de serie temporal |
| ≥2 años distintos presentes | `interannual` | Comparación mismo mes vs. año anterior |

## 7. Fases de evolución (sin romper el núcleo)

```
FASE 1  1 parcela, 1 vuelo               → HTML estático (baseline)
FASE 2  2+ vuelos                        → comparación automática
FASE 3  3+ vuelos                        → serie temporal
FASE 4  12 meses                         → resumen mensual + anual
FASE 5  múltiples parcelas               → ya soportado por la jerarquía de carpetas
FASE 6  múltiples clientes               → ya soportado por la jerarquía de carpetas
FASE 7  histórico multianual             → comparación interanual (temporal.py)
FASE 8  PostGIS + API + servidor         → migración de JSON a tablas, mismo modelo conceptual
```

Ninguna de estas fases requiere cambiar el esquema de `flights[]`, el CLI,
ni el formato de `dashboard.json`.

## 8. Sensores e índices

El sensor actual es RGB. El índice principal comunicado al usuario final es
VARI, presentado siempre como *"índice de verdor derivado de imágenes RGB"*,
nunca como sustituto de NDVI. `ixdron/pipeline/indices.py` mantiene un
registro `{índice: {bandas_requeridas, función}}`; añadir NDVI/GNDVI/NDRE
cuando exista un sensor multiespectral es agregar una entrada a ese
registro, sin tocar el resto del pipeline.

## 9. Motor de reglas

`ixdron/pipeline/rules.py` nunca afirma causalidad. Cada regla evaluada
produce tres campos siempre separados:

- **Observación**: el hecho medido ("disminuyó X% del área").
- **Interpretación**: causas posibles, sin afirmar cuál ocurrió.
- **Recomendación**: acción sugerida (típicamente, inspección de campo).

Las reglas son datos (lista de diccionarios), pensadas para moverse a un
`config/rules.json` editable por caso de uso (agricultura, conservación,
restauración, etc.) sin tocar código.
