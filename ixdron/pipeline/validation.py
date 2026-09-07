"""
IX DRON - pipeline.validation

Punto 26 del prompt: nunca generar un resultado falso. Toda validación que
falle debe producir un mensaje explícito, no un silencio ni un cálculo
inventado.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
import json

import rasterio
from rasterio.warp import transform_bounds


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def validate_orthophoto(path: Path) -> ValidationResult:
    """Valida que el GeoTIFF exista, tenga CRS, geotransformación y datos válidos."""
    result = ValidationResult(ok=True)

    if not path or not path.exists():
        result.ok = False
        result.errors.append(f"No se encontró ortofoto en {path}")
        return result

    try:
        with rasterio.open(path) as src:
            if src.crs is None:
                result.ok = False
                result.errors.append("El raster no tiene CRS definido.")
            if src.transform is None or src.transform.is_identity:
                result.ok = False
                result.errors.append("El raster no tiene geotransformación válida.")
            if src.width == 0 or src.height == 0:
                result.ok = False
                result.errors.append("El raster tiene dimensiones inválidas (0 px).")
            if src.count < 3:
                result.warnings.append(
                    f"El raster tiene solo {src.count} banda(s); se esperaban al menos 3 (RGB)."
                )
    except Exception as e:  # noqa: BLE001
        result.ok = False
        result.errors.append(f"No se pudo abrir el raster: {e}")

    return result


def validate_parcel_boundary(boundary_path: Path) -> ValidationResult:
    result = ValidationResult(ok=True)
    if not boundary_path.exists():
        result.ok = False
        result.errors.append(f"No existe parcel_boundary.geojson en {boundary_path}")
        return result
    try:
        geo = json.loads(boundary_path.read_text())
        if "features" not in geo or not geo["features"]:
            result.ok = False
            result.errors.append("parcel_boundary.geojson no contiene geometrías.")
    except Exception as e:  # noqa: BLE001
        result.ok = False
        result.errors.append(f"parcel_boundary.geojson inválido: {e}")
    return result


def validate_geometry_overlap(ortho_path: Path, boundary_path: Path) -> ValidationResult:
    """
    Verifica que el polígono de la parcela realmente se solape con el
    ortomosaico, reproyectando ambos a un CRS común (EPSG:4326) antes de
    comparar. Esto detecta a tiempo el error más común al conectar datos
    reales: dibujar `parcel_boundary.geojson` (en lat/lon) sobre una
    ortofoto que ODM georreferenció en un CRS proyectado distinto, o
    simplemente dibujar el polígono sobre el lugar equivocado.
    """
    result = ValidationResult(ok=True)
    try:
        with rasterio.open(ortho_path) as src:
            raster_bounds_4326 = transform_bounds(src.crs, "EPSG:4326", *src.bounds)

        geo = json.loads(boundary_path.read_text())
        xs, ys = [], []
        for feature in geo.get("features", []):
            geom = feature["geometry"]
            coords = geom["coordinates"]
            # Aplana coordenadas de Polygon/MultiPolygon a una lista de (x,y)
            stack = [coords]
            while stack:
                c = stack.pop()
                if isinstance(c[0], (int, float)):
                    xs.append(c[0]); ys.append(c[1])
                else:
                    stack.extend(c)

        if not xs:
            result.ok = False
            result.errors.append("No se encontraron coordenadas en parcel_boundary.geojson.")
            return result

        boundary_bounds = (min(xs), min(ys), max(xs), max(ys))

        inter_minx = max(raster_bounds_4326[0], boundary_bounds[0])
        inter_miny = max(raster_bounds_4326[1], boundary_bounds[1])
        inter_maxx = min(raster_bounds_4326[2], boundary_bounds[2])
        inter_maxy = min(raster_bounds_4326[3], boundary_bounds[3])

        if inter_minx >= inter_maxx or inter_miny >= inter_maxy:
            result.ok = False
            result.errors.append(
                "El polígono de parcel_boundary.geojson no se solapa con el "
                "área del ortomosaico. Verifica que el polígono esté dibujado "
                "sobre la ubicación real de la parcela (en EPSG:4326 / "
                "lat-lon, como exporta geojson.io) y que la ortofoto de ODM "
                f"esté correctamente georreferenciada. "
                f"Ortofoto (lat/lon): {tuple(round(v, 5) for v in raster_bounds_4326)} · "
                f"Parcela (lat/lon): {tuple(round(v, 5) for v in boundary_bounds)}."
            )
    except Exception as e:  # noqa: BLE001
        result.ok = False
        result.errors.append(f"No se pudo verificar el solapamiento parcela/ortofoto: {e}")

    return result


def check_comparability(path_a: Path, path_b: Path) -> ValidationResult:
    """
    Verifica que dos rasters (vuelo actual vs. anterior) sean comparables:
    mismo CRS "equivalente" (comparado en un CRS común) y solapamiento espacial.
    No exige idéntica resolución de píxel (se remuestrea en raster_utils),
    pero sí advierte si la diferencia de resolución es grande.
    """
    result = ValidationResult(ok=True)
    try:
        with rasterio.open(path_a) as a, rasterio.open(path_b) as b:
            bounds_a = transform_bounds(a.crs, "EPSG:4326", *a.bounds)
            bounds_b = transform_bounds(b.crs, "EPSG:4326", *b.bounds)

            # Intersección simple de bounding boxes en EPSG:4326
            inter_minx = max(bounds_a[0], bounds_b[0])
            inter_miny = max(bounds_a[1], bounds_b[1])
            inter_maxx = min(bounds_a[2], bounds_b[2])
            inter_maxy = min(bounds_a[3], bounds_b[3])

            if inter_minx >= inter_maxx or inter_miny >= inter_maxy:
                result.ok = False
                result.errors.append(
                    "Los vuelos no se solapan espacialmente; no son comparables."
                )
                return result

            res_a = abs(a.transform.a)
            res_b = abs(b.transform.a)
            if res_a > 0 and res_b > 0:
                ratio = max(res_a, res_b) / min(res_a, res_b)
                if ratio > 2:
                    result.warnings.append(
                        f"Diferencia de resolución significativa entre vuelos "
                        f"({res_a:.3f} vs {res_b:.3f} m/px)."
                    )
    except Exception as e:  # noqa: BLE001
        result.ok = False
        result.errors.append(f"No se pudo evaluar comparabilidad: {e}")

    return result
