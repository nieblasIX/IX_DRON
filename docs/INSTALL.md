# Instalación

## Requisitos

- Python 3.10+
- WebODM o ODM instalado por separado (no forma parte de este repositorio;
  IX DRON consume sus productos, no reemplaza el procesamiento fotogramétrico)
- Git

## Pasos

```bash
git clone <url-del-repositorio> ixdron
cd ixdron
pip install -r requirements.txt --break-system-packages   # o dentro de un venv
```

Dependencias (`requirements.txt`): `numpy`, `pillow`, `rasterio`. Todas son
open source, sin costo de licencia.

## Verificar la instalación con los datos de demostración

```bash
python3 scripts/generate_demo_data.py
PYTHONPATH=. python3 -m ixdron.cli process
cd web/dashboard && python3 -m http.server 8000
```

Abrir `http://localhost:8000` en el navegador. Deberías ver la parcela de
demostración con 3 vuelos, comparación automática y serie temporal.

> Los datos de demo son sintéticos (generados matemáticamente, no son fotos
> reales de dron) y sirven únicamente para validar que el pipeline completo
> funciona en tu entorno antes de conectar vuelos reales.

## Preparar tu primera parcela real

```bash
mkdir -p data/clientes/MI_CLIENTE/parcelas/MI_PARCELA/flights
```

Dentro de `MI_PARCELA/`, crea:

1. `parcel_boundary.geojson` — un FeatureCollection con un único polígono
   que delimite la parcela (puede dibujarse en geojson.io y exportarse).
2. `parcel_config.json` (opcional, ver `docs/USAGE.md` para el formato).

## Publicación en GitHub Pages (costo cero)

1. Crear un repositorio en GitHub.
2. Empujar **solo** la carpeta `web/dashboard/` a la rama que sirve
   GitHub Pages (recomendado: repositorio separado del que contiene
   `data/`, por privacidad — ver `docs/ARCHITECTURE.md` §8).
3. En la configuración del repositorio → Pages → seleccionar la rama y
   carpeta raíz.
4. El sitio queda disponible en `https://<usuario>.github.io/<repo>/`.

Cada vez que se ejecuta `ixdron process`, se debe volver a subir
(`git add web/dashboard/data && git commit && git push`) para que el
sitio público se actualice. Este paso puede automatizarse más adelante
con una GitHub Action (fuera del alcance del MVP, no bloqueado por la
arquitectura actual).
