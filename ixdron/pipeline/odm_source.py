"""
IX DRON - pipeline.odm_source

Este módulo permite que IX DRON lea DIRECTAMENTE la estructura de carpetas
que produce una corrida de ODM/WebODM en disco, sin que el operador tenga
que copiar, mover o renombrar nada.

Estructura real observada (ejemplo del cliente):

    SAN_AGUSTIN_ZAPOTLAN/                      <- raw_flights_root (una parcela)
      SAZ_JOSE_2026_09_03/                     <- carpeta de vuelo (nombre libre + fecha)
        SAZ_JOSE/                              <- carpeta de proyecto ODM
          images/
          odm_orthophoto/
            odm_orthophoto.tif                 <- ortomosaico
          odm_dem/
            dsm.tif                            <- DSM (si --dsm estaba activo)
          odm_georeferencing/
          cameras.json
          images.json
          log.json
          options.json
          benchmark.txt

IX DRON NO copia estos archivos pesados a su propio árbol de datos: el
GeoTIFF master permanece donde ODM lo dejó (punto 6 del prompt original:
"el GeoTIFF original debe conservarse como producto científico/master").
Lo único que IX DRON escribe en `data/clientes/.../flights/{fecha}/` es:

    source.json      -> ruta absoluta al proyecto ODM real (trazabilidad)
    metadata.json     -> metadata extraída de log.json/options.json/cameras.json
    analysis/          -> productos derivados livianos (vari.tif, previews, stats.json)

Esto mantiene el árbol de datos de IX DRON pequeño y apto para git, incluso
si las carpetas de ODM ocupan decenas de GB en el disco del operador.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from ixdron.models.schemas import FlightMetadata

# Nombres de archivo estándar que usa ODM/WebODM para sus productos.
ODM_ORTHOPHOTO_SUBDIR = "odm_orthophoto"
ODM_ORTHOPHOTO_FILENAMES = ("odm_orthophoto.tif", "odm_orthophoto.original.tif")
ODM_DEM_SUBDIR = "odm_dem"
ODM_DEM_FILENAMES = ("dsm.tif",)
ODM_DTM_FILENAMES = ("dtm.tif",)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".tif", ".tiff", ".png")

# Patrones de fecha aceptados al final (o dentro) del nombre de la carpeta
# de vuelo. Se prueban en orden; el primero que haga match gana.
# Ejemplos que debe reconocer:
#   "SAZ_JOSE_2026_09_03"  -> 2026-09-03
#   "2026-09-03"            -> 2026-09-03  (convención usada en el MVP/demo)
#   "vuelo_20260903"        -> 2026-09-03
_DATE_PATTERNS = [
    re.compile(r"(\d{4})_(\d{2})_(\d{2})$"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})$"),
    re.compile(r"(\d{4})(\d{2})(\d{2})$"),
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"),
]


def parse_flight_date(folder_name: str) -> Optional[str]:
    """
    Intenta extraer una fecha ISO (AAAA-MM-DD) del nombre de una carpeta de
    vuelo, sin importar qué prefijo (proyecto, operador, parcela) la
    acompañe. Devuelve None si no se reconoce ningún patrón de fecha.
    """
    for pattern in _DATE_PATTERNS:
        m = pattern.search(folder_name)
        if m:
            year, month, day = m.groups()
            try:
                datetime(int(year), int(month), int(day))
                return f"{year}-{month}-{day}"
            except ValueError:
                continue
    return None


def find_odm_project_dir(flight_raw_dir: Path) -> Optional[Path]:
    """
    Dentro de la carpeta de un vuelo, localiza el directorio de proyecto de
    ODM (el que contiene `odm_orthophoto/`). Contempla dos casos:
      a) ODM corrió directamente dentro de flight_raw_dir
         (flight_raw_dir/odm_orthophoto/...)
      b) ODM corrió dentro de una subcarpeta de proyecto
         (flight_raw_dir/{proyecto}/odm_orthophoto/...)  <- caso del cliente
    """
    if (flight_raw_dir / ODM_ORTHOPHOTO_SUBDIR).exists():
        return flight_raw_dir

    if not flight_raw_dir.is_dir():
        return None

    for sub in sorted(flight_raw_dir.iterdir()):
        if sub.is_dir() and (sub / ODM_ORTHOPHOTO_SUBDIR).exists():
            return sub

    return None


def find_orthophoto_in_project(project_dir: Path) -> Optional[Path]:
    ortho_dir = project_dir / ODM_ORTHOPHOTO_SUBDIR
    if not ortho_dir.exists():
        return None
    for fname in ODM_ORTHOPHOTO_FILENAMES:
        candidate = ortho_dir / fname
        if candidate.exists():
            return candidate
    # Fallback: cualquier .tif dentro de odm_orthophoto/
    tifs = list(ortho_dir.glob("*.tif"))
    return tifs[0] if tifs else None


def find_dsm_in_project(project_dir: Path) -> Optional[Path]:
    dem_dir = project_dir / ODM_DEM_SUBDIR
    if not dem_dir.exists():
        return None
    for fname in ODM_DEM_FILENAMES:
        candidate = dem_dir / fname
        if candidate.exists():
            return candidate
    return None


def count_source_images(project_dir: Path) -> Optional[int]:
    images_dir = project_dir / "images"
    if not images_dir.exists():
        return None
    return sum(1 for p in images_dir.iterdir()
               if p.suffix.lower() in IMAGE_EXTENSIONS)


def read_json_safe(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return {}


def describe_camera(project_dir: Path) -> Optional[str]:
    """
    cameras.json de ODM tiene la forma {"<descriptor de cámara>": {...}}.
    Se usa la(s) clave(s) como descripción legible; su formato varía entre
    versiones de ODM, por eso se maneja de forma defensiva.
    """
    cams = read_json_safe(project_dir / "cameras.json")
    if not cams:
        return None
    keys = list(cams.keys())
    return "; ".join(keys) if keys else None


def extract_processing_params(project_dir: Path) -> dict:
    """Lee options.json (parámetros con los que se ejecutó ODM)."""
    return read_json_safe(project_dir / "options.json")


def sync_flights_from_raw_root(parcel_path: Path, raw_root: Path,
                                parcel_id: str, client_id: str) -> List[Path]:
    """
    Escanea `raw_root` (carpeta con una subcarpeta por vuelo, salida cruda
    de ODM) y crea/actualiza la carpeta liviana correspondiente en
    `parcel_path/flights/{fecha}/`, con `source.json` apuntando al proyecto
    ODM real y `metadata.json` con los datos extraídos.

    Devuelve la lista de carpetas de vuelo locales sincronizadas.
    """
    synced = []
    if not raw_root.exists():
        return synced

    for flight_raw_dir in sorted(raw_root.iterdir()):
        if not flight_raw_dir.is_dir():
            continue

        flight_date = parse_flight_date(flight_raw_dir.name)
        if flight_date is None:
            print(f"  [omitido] no se pudo determinar la fecha de '{flight_raw_dir.name}' "
                  f"(se esperaba un patrón AAAA_MM_DD o AAAA-MM-DD en el nombre)")
            continue

        project_dir = find_odm_project_dir(flight_raw_dir)
        local_flight_dir = parcel_path / "flights" / flight_date
        local_flight_dir.mkdir(parents=True, exist_ok=True)

        source_info = {
            "raw_flight_dir": str(flight_raw_dir.resolve()),
            "odm_project_dir": str(project_dir.resolve()) if project_dir else None,
            "synced_at": datetime.utcnow().isoformat(),
        }
        (local_flight_dir / "source.json").write_text(
            json.dumps(source_info, indent=2, ensure_ascii=False)
        )

        _refresh_metadata_from_odm(local_flight_dir, project_dir, flight_date,
                                    parcel_id, client_id)
        synced.append(local_flight_dir)

    return synced


def _refresh_metadata_from_odm(local_flight_dir: Path, project_dir: Optional[Path],
                                flight_date: str, parcel_id: str, client_id: str) -> None:
    meta_file = local_flight_dir / "metadata.json"
    if meta_file.exists():
        meta = FlightMetadata(**json.loads(meta_file.read_text()))
    else:
        meta = FlightMetadata(
            flight_id=flight_date, parcel_id=parcel_id, client_id=client_id,
            date=flight_date, status="pending",
        )

    if project_dir is not None:
        meta.n_images = count_source_images(project_dir) or meta.n_images
        meta.camera = describe_camera(project_dir) or meta.camera
        params = extract_processing_params(project_dir)
        if params:
            meta.processing_params = params

        ortho = find_orthophoto_in_project(project_dir)
        if ortho is not None:
            try:
                import rasterio
                with rasterio.open(ortho) as src:
                    meta.crs = str(src.crs) if src.crs else meta.crs
                    meta.resolution = f"{src.width}x{src.height}"
                    # GSD real, calculado del propio raster (más confiable
                    # que cualquier valor reportado en log.json/options.json)
                    if src.crs and src.crs.is_projected:
                        meta.gsd_cm = round(abs(src.transform.a) * 100, 2)
                    elif src.crs:
                        # CRS geográfico (grados): aproximar a metros en el
                        # ecuador solo como referencia informativa.
                        meta.gsd_cm = round(abs(src.transform.a) * 111000 * 100, 2)
            except Exception:  # noqa: BLE001
                pass

        dsm = find_dsm_in_project(project_dir)
        meta.processing_params["dsm_available"] = dsm is not None

    meta_file.write_text(json.dumps(meta.to_dict(), indent=2, ensure_ascii=False))
