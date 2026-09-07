# IX DRON — Bitácora Viva de la Parcela

Sistema de monitoreo aéreo, ambiental y temporal de parcelas a partir de
vuelos periódicos con dron RGB. Convierte fotografías de dron (procesadas
por WebODM/ODM) en un dashboard web estático, publicable en GitHub Pages,
que responde: *¿cómo está mi parcela, qué cambió, desde cuándo y qué
debería revisar?*

## Estado de este entregable

Este repositorio contiene un **MVP funcional completo y probado
end-to-end**, con datos sintéticos de demostración (no hay fotografías de
dron reales disponibles en este entorno de desarrollo). El pipeline,
el modelo de datos y el dashboard son productivos: solo falta apuntarlos
a ortofotos reales generadas por WebODM.

Ejecutado y verificado:
- 3 vuelos sintéticos procesados de punta a punta (`ixdron process`).
- Detección automática de vuelo de referencia → comparación → serie temporal.
- Motor de reglas generando observación/interpretación/recomendación.
- Dashboard renderizado sin errores (Leaflet + Plotly, verificado con
  Playwright/Chromium headless), 100% autocontenido (sin CDNs externos).

## Estructura del repositorio

```
ixdron/                    Paquete Python (el pipeline)
  config.py                 Rutas y parámetros globales
  cli.py                    Interfaz de línea de comandos (ixdron process/build/list)
  models/schemas.py         Modelo de datos (CLIENT→PARCEL→FLIGHT→...)
  pipeline/
    ingestion.py             Descubre vuelos y localiza el ortomosaico ODM
    validation.py            Valida raster, geometría y comparabilidad
    raster_utils.py          Recorte, remuestreo, previews web
    indices.py                Registro de índices RGB (VARI/ExG/GLI)
    statistics.py             Estadísticas descriptivas por vuelo
    change_detection.py       Comparación vuelo actual vs. anterior
    temporal.py                Series y agregados (semana/mes/año) derivados
    rules.py                    Motor de reglas → recomendaciones
    orchestrator.py             Orquesta el procesamiento de un vuelo/parcela
    web_assets.py                Genera los JSON que consume el dashboard

data/clientes/                  Datos de cada cliente/parcela (NO subir a un
                                  repo público sin revisar el punto 30 de
                                  privacidad de docs/ARCHITECTURE.md)
web/dashboard/                  Sitio estático (esto es lo que se publica)
  index.html, assets/css, assets/js, assets/vendor (Leaflet y Plotly locales)
  data/                          JSON y previews generados por el pipeline
                                  (NUNCA editar a mano)

scripts/generate_demo_data.py   Genera la parcela y los 3 vuelos de demo
docs/                            Documentación ampliada
```

## Inicio rápido

```bash
pip install -r requirements.txt
python3 scripts/generate_demo_data.py      # genera datos de demo (opcional)
PYTHONPATH=. python3 -m ixdron.cli process  # ejecuta el pipeline completo
cd web/dashboard && python3 -m http.server 8000
# abrir http://localhost:8000
```

Ver `docs/INSTALL.md` y `docs/USAGE.md` para el flujo con vuelos reales
(WebODM) y `docs/ARCHITECTURE.md` para las decisiones de diseño, riesgos
identificados y la estrategia de escalamiento multianual/multi-parcela.

## Principio del sistema

No es un dashboard: es una bitácora temporal. Cada vuelo es una observación
que se agrega a `flights[]`; las vistas (semana/mes/año/histórico) se
derivan de esa lista, nunca se almacenan por separado. Esto es lo que
permite que el mismo código funcione igual con 1 vuelo que con 200, y con
1 parcela que con 50.
