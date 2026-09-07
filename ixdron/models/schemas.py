"""
IX DRON - Modelo de datos.

Estas dataclasses representan las entidades conceptuales del sistema:

    CLIENT -> PROJECT -> PARCEL -> FLIGHT -> RASTER -> INDEX -> STATISTIC
           -> CHANGE_DETECTION -> REPORT -> RECOMMENDATION -> OBSERVATION

Se implementan hoy como JSON plano en disco, pero los nombres de campo son
deliberadamente los mismos que tendrían las columnas de una futura base
PostGIS, para que la migración sea un mapeo directo y no una reescritura.

IMPORTANTE: estas clases son documentación ejecutable del esquema, no un ORM.
El pipeline lee/escribe diccionarios; usar `asdict()` para serializar.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class ParcelConfig:
    """Configuración persistente de una parcela (PARCEL)."""
    parcel_id: str
    client_id: str
    name: str
    use_case: str = "agriculture"  # agricultura, conservacion, restauracion, etc.
    boundary_file: str = "parcel_boundary.geojson"
    area_ha: Optional[float] = None
    crs: Optional[str] = None
    change_thresholds: Dict[str, float] = field(default_factory=dict)
    sensor_bands: List[str] = field(default_factory=lambda: ["R", "G", "B"])
    created_at: Optional[str] = None


@dataclass
class FlightMetadata:
    """Metadata mínima obligatoria por vuelo (FLIGHT). Punto 4 del prompt."""
    flight_id: str                  # p.ej. "2026-09-03"
    parcel_id: str
    client_id: str
    date: str                       # ISO date
    time: Optional[str] = None
    altitude_m: Optional[float] = None
    gsd_cm: Optional[float] = None
    camera: Optional[str] = None
    n_images: Optional[int] = None
    resolution: Optional[str] = None
    crs: Optional[str] = None
    coverage_pct: Optional[float] = None
    processing_params: Dict[str, Any] = field(default_factory=dict)
    pipeline_version: Optional[str] = None
    processed_at: Optional[str] = None
    status: str = "pending"  # pending | baseline | processed | failed
    status_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RasterProduct:
    """Producto raster derivado de un vuelo (RASTER)."""
    flight_id: str
    kind: str            # orthophoto | dsm | pointcloud | index | change
    master_path: str     # ruta al archivo científico original (nunca se borra)
    web_preview_path: Optional[str] = None
    crs: Optional[str] = None
    bounds: Optional[List[float]] = None  # [minx, miny, maxx, maxy] en EPSG:4326
    pixel_size: Optional[float] = None
    size_mb: Optional[float] = None


@dataclass
class IndexResult:
    """Resultado de calcular un índice RGB/multiespectral (INDEX)."""
    flight_id: str
    index_name: str      # VARI | ExG | GLI | NDVI (futuro) ...
    sensor_bands_used: List[str]
    raster_path: str


@dataclass
class StatisticRecord:
    """Estadísticas de un vuelo para un índice dado (STATISTIC)."""
    flight_id: str
    date: str
    index_name: str
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    p10: Optional[float] = None
    p90: Optional[float] = None
    vegetation_cover_pct: Optional[float] = None
    valid_area_pct: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangeDetectionRecord:
    """Comparación entre dos vuelos (CHANGE_DETECTION)."""
    flight_id_current: str
    flight_id_previous: str
    comparison_type: str  # "sequential" | "interannual" | "same_period_last_year"
    index_name: str
    mean_delta: Optional[float] = None
    pct_area_increase: Optional[float] = None
    pct_area_stable: Optional[float] = None
    pct_area_decrease: Optional[float] = None
    threshold_used: Optional[float] = None
    change_raster_path: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class Recommendation:
    """Salida del motor de reglas (RECOMMENDATION), separando siempre
    observación (hecho medido) de interpretación (posibles causas) de
    recomendación (acción sugerida)."""
    flight_id: str
    rule_id: str
    observation: str
    interpretation: str
    recommendation: str
    severity: str = "info"  # info | attention | priority
