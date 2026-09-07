"""
IX DRON - pipeline.ingestion

Responsable de:
  1. Descubrir vuelos dentro de una parcela (carpetas /flights/{fecha}/).
  2. Detectar si ya existe un producto ODM/WebODM procesado o si hace falta
     lanzar el procesamiento fotogramétrico (hook, no implementado en el MVP:
     se asume que WebODM ya corrió y dejó sus productos en
     flights/{fecha}/odm/products/).
  3. Cargar / crear metadata.json del vuelo.

Este módulo NO calcula índices ni estadísticas: solo localiza insumos.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from ixdron.config import SUPPORTED_ORTHO_EXTENSIONS, IXDRON_PIPELINE_VERSION
from ixdron.models.schemas import FlightMetadata


def discover_flights(parcel_path: Path) -> list[Path]:
    """Devuelve las carpetas de vuelo existentes, ordenadas por fecha (nombre)."""
    flights_dir = parcel_path / "flights"
    if not flights_dir.exists():
        return []
    return sorted([p for p in flights_dir.iterdir() if p.is_dir()])


def find_orthophoto(flight_path: Path) -> Optional[Path]:
    """
    Localiza el ortomosaico del vuelo, en este orden de prioridad:
      1. Si existe source.json (vuelo sincronizado desde una corrida real
         de ODM/WebODM, ver pipeline.odm_source), usar esa ruta directamente.
      2. flights/{fecha}/odm/products/*.tif  (convención simplificada / demo)
      3. flights/{fecha}/products/*.tif      (producto ya colocado a mano)
    Devuelve el primer GeoTIFF encontrado o None si no existe.
    """
    from ixdron.pipeline import odm_source

    source_file = flight_path / "source.json"
    if source_file.exists():
        info = json.loads(source_file.read_text())
        project_dir = info.get("odm_project_dir")
        if project_dir:
            ortho = odm_source.find_orthophoto_in_project(Path(project_dir))
            if ortho:
                return ortho

    candidates = []
    for sub in ("odm/products", "products"):
        d = flight_path / sub
        if d.exists():
            candidates.extend(
                p for p in d.iterdir()
                if p.suffix.lower() in SUPPORTED_ORTHO_EXTENSIONS
            )
    if not candidates:
        return None
    # Preferir archivos con "ortho" en el nombre si existen varios
    ortho = [c for c in candidates if "ortho" in c.name.lower()]
    return (ortho or candidates)[0]


def find_dsm(flight_path: Path) -> Optional[Path]:
    """Igual que find_orthophoto pero para el DSM, cuando esté disponible."""
    from ixdron.pipeline import odm_source

    source_file = flight_path / "source.json"
    if source_file.exists():
        info = json.loads(source_file.read_text())
        project_dir = info.get("odm_project_dir")
        if project_dir:
            return odm_source.find_dsm_in_project(Path(project_dir))
    return None


def load_or_init_metadata(flight_path: Path, parcel_id: str, client_id: str) -> FlightMetadata:
    """Carga metadata.json existente o crea una estructura mínima nueva."""
    meta_file = flight_path / "metadata.json"
    flight_id = flight_path.name

    if meta_file.exists():
        raw = json.loads(meta_file.read_text())
        return FlightMetadata(**raw)

    meta = FlightMetadata(
        flight_id=flight_id,
        parcel_id=parcel_id,
        client_id=client_id,
        date=flight_id,  # convención: nombre de carpeta = fecha ISO
        status="pending",
    )
    save_metadata(flight_path, meta)
    return meta


def save_metadata(flight_path: Path, meta: FlightMetadata) -> None:
    meta_file = flight_path / "metadata.json"
    meta_file.write_text(json.dumps(meta.to_dict(), indent=2, ensure_ascii=False))


def mark_processed(flight_path: Path, meta: FlightMetadata, status: str,
                    reason: Optional[str] = None) -> FlightMetadata:
    meta.status = status
    meta.status_reason = reason
    meta.pipeline_version = IXDRON_PIPELINE_VERSION
    meta.processed_at = datetime.utcnow().isoformat()
    save_metadata(flight_path, meta)
    return meta
