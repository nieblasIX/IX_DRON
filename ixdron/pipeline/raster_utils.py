"""
IX DRON - pipeline.raster_utils

Operaciones raster de bajo nivel: lectura, recorte a la geometría de la
parcela, remuestreo a una rejilla común para comparación, y generación de
previews ligeros para la web (Punto 6: no servir el TIFF completo).
"""
from __future__ import annotations
from pathlib import Path
from typing import Tuple
import json

import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from PIL import Image

from ixdron.config import DEFAULT_WEB_PREVIEW_MAX_PIXELS


def load_rgb_masked(ortho_path: Path, boundary_geojson: Path) -> Tuple[np.ndarray, dict, dict]:
    """
    Carga las bandas RGB de la ortofoto recortadas a la geometría de la
    parcela. Devuelve (array [3,H,W] float32 en 0-255, profile, bounds_4326).

    IMPORTANTE: parcel_boundary.geojson se dibuja típicamente en herramientas
    como geojson.io, que exportan siempre en EPSG:4326 (lat/lon), mientras
    que el ortomosaico de ODM normalmente está en un CRS proyectado (p. ej.
    UTM, en metros). Por eso la geometría SIEMPRE se reproyecta al CRS del
    raster antes de recortar — nunca se asume que ya coinciden.
    """
    from rasterio.warp import transform_geom

    geo = json.loads(boundary_geojson.read_text())
    geoms_4326 = [f["geometry"] for f in geo["features"]]

    with rasterio.open(ortho_path) as src:
        geoms = [transform_geom("EPSG:4326", src.crs, g) for g in geoms_4326]
        out_image, out_transform = rio_mask(src, geoms, crop=True, nodata=0)
        profile = src.profile.copy()
        profile.update({
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
        })
        bands = out_image[:3].astype("float32")

        from rasterio.warp import transform_bounds
        new_bounds = rasterio.transform.array_bounds(
            out_image.shape[1], out_image.shape[2], out_transform
        )
        bounds_4326 = transform_bounds(src.crs, "EPSG:4326", *new_bounds)

    return bands, profile, {
        "minx": bounds_4326[0], "miny": bounds_4326[1],
        "maxx": bounds_4326[2], "maxy": bounds_4326[3],
    }


def save_index_geotiff(index_array: np.ndarray, profile: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    p = profile.copy()
    p.update(count=1, dtype="float32", nodata=np.nan)
    with rasterio.open(out_path, "w", **p) as dst:
        dst.write(index_array.astype("float32"), 1)


def array_to_web_png(array: np.ndarray, out_path: Path, cmap: str = "gray",
                      vmin: float = None, vmax: float = None) -> Tuple[float, float] | None:
    """
    Convierte un array 2D (índice) o 3D (RGB) a un PNG optimizado para web,
    con un tamaño máximo de lado definido en config.DEFAULT_WEB_PREVIEW_MAX_PIXELS.

    Para arrays 2D (índices), devuelve el (vmin, vmax) efectivamente usado
    para normalizar los colores — necesario para poder dibujar una leyenda
    de color honesta en el dashboard (Punto: "no sale una barra de colores
    que explique el espectro"). Para RGB devuelve None (no aplica).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if array.ndim == 3:
        # RGB: (3,H,W) -> (H,W,3) normalizado a 0-255
        rgb = np.transpose(array, (1, 2, 0))
        rgb = np.clip(rgb, 0, 255).astype("uint8")
        img = Image.fromarray(rgb, mode="RGB")
        used_range = None
    else:
        data = array.copy()
        valid = np.isfinite(data)
        if vmin is None:
            vmin = float(np.nanpercentile(data[valid], 2)) if valid.any() else 0.0
        if vmax is None:
            vmax = float(np.nanpercentile(data[valid], 98)) if valid.any() else 1.0
        used_range = (round(vmin, 4), round(vmax, 4))
        norm = np.clip((data - vmin) / (vmax - vmin + 1e-9), 0, 1)
        norm = np.nan_to_num(norm, nan=0.0)

        colored = apply_colormap(norm, cmap)
        alpha = (valid * 255).astype("uint8")
        rgba = np.dstack([colored, alpha])
        img = Image.fromarray(rgba, mode="RGBA")

    # Downscale si excede el máximo definido
    max_side = max(img.size)
    if max_side > DEFAULT_WEB_PREVIEW_MAX_PIXELS:
        scale = DEFAULT_WEB_PREVIEW_MAX_PIXELS / max_side
        new_size = (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale)))
        img = img.resize(new_size, Image.BILINEAR)

    img.save(out_path, optimize=True)
    return used_range


def apply_colormap(norm: np.ndarray, cmap: str) -> np.ndarray:
    """Colormap manual simple (evita dependencia de matplotlib)."""
    if cmap == "vari":
        # rojo (bajo) -> amarillo -> verde (alto): apto para índice de verdor
        r = np.clip(1.5 - 2 * norm, 0, 1)
        g = np.clip(2 * norm, 0, 1)
        b = np.zeros_like(norm)
    elif cmap == "change":
        # rojo (disminución) - blanco (estable) - verde (incremento)
        centered = norm - 0.5
        r = np.clip(1 - 2 * np.clip(centered, 0, 0.5) - 2 * np.clip(-centered, -0.5, 0), 0, 1)
        r = np.clip(0.5 - centered, 0, 1) * 2
        r = np.clip(r, 0, 1)
        g = np.clip(0.5 + centered, 0, 1) * 2
        g = np.clip(g, 0, 1)
        b = np.clip(1 - np.abs(centered) * 2, 0, 1)
    else:  # gray
        r = g = b = norm
    stacked = np.dstack([r, g, b])
    return (stacked * 255).astype("uint8")


def align_to_reference(array: np.ndarray, profile: dict,
                        ref_profile: dict) -> np.ndarray:
    """
    Remuestrea `array` (con su `profile`) a la rejilla de `ref_profile`
    (mismo CRS/transform/tamaño), para poder restar dos vuelos píxel a píxel.
    """
    dst = np.zeros((ref_profile["height"], ref_profile["width"]), dtype="float32")
    reproject(
        source=array,
        destination=dst,
        src_transform=profile["transform"],
        src_crs=profile["crs"],
        dst_transform=ref_profile["transform"],
        dst_crs=ref_profile["crs"],
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    return dst


def pixel_size_meters(profile: dict, center_lat_deg: float = None) -> float:
    """
    Devuelve el tamaño de píxel en metros, sin depender de pyproj:
      - Si el CRS es proyectado (el caso normal de un ortomosaico de ODM,
        típicamente UTM), el tamaño de píxel YA está en metros.
      - Si el CRS es geográfico (grados, como en los datos sintéticos de
        demo), se aproxima usando 111,320 m/grado corregido por la latitud
        (suficiente para parcelas pequeñas; no es geodésicamente exacto).
    """
    transform = profile["transform"]
    px = abs(transform.a)
    crs = profile.get("crs")
    if crs is not None and crs.is_geographic:
        lat = center_lat_deg if center_lat_deg is not None else 0.0
        return px * 111320 * np.cos(np.radians(lat))
    return px


def compute_area_ha(profile: dict, valid_pixel_count: int,
                     center_lat_deg: float = None) -> float:
    """Área (hectáreas) cubierta por los píxeles válidos de una máscara."""
    px_m = pixel_size_meters(profile, center_lat_deg)
    return float(valid_pixel_count * (px_m ** 2) / 10000.0)
