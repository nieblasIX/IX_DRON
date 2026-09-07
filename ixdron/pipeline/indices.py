"""
IX DRON - pipeline.indices

Punto 7 del prompt: el sensor inicial es RGB. NO se debe presentar NDVI como
disponible. Este módulo separa explícitamente:

    sensor/bandas disponibles  ->  algoritmo del índice  ->  producto

de forma que añadir un sensor multiespectral en el futuro (NDVI, GNDVI, NDRE,
NDWI) sea registrar una función nueva aquí, sin tocar el resto del pipeline.

Todas las funciones reciben un array [bands, H, W] en 0-255 (float) y bandas
en el orden que declara `sensor_bands` (por defecto ["R","G","B"]).
"""
from __future__ import annotations
import numpy as np
from typing import Callable, Dict, List

IndexFunc = Callable[[np.ndarray, Dict[str, int]], np.ndarray]


def _get_band(arr: np.ndarray, band_index: Dict[str, int], name: str) -> np.ndarray:
    return arr[band_index[name]]


def vari(arr: np.ndarray, band_index: Dict[str, int]) -> np.ndarray:
    """
    VARI - Visible Atmospherically Resistant Index.
    VARI = (G - R) / (G + R - B)
    Rango teórico aprox. [-1, 1]; valores más altos = mayor "verdor" relativo.
    Presentado al usuario final como "Índice de verdor derivado de RGB",
    NUNCA como sustituto de NDVI.
    """
    r = _get_band(arr, band_index, "R")
    g = _get_band(arr, band_index, "G")
    b = _get_band(arr, band_index, "B")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (g - r) / (g + r - b)
    out[~np.isfinite(out)] = np.nan
    return out


def exg(arr: np.ndarray, band_index: Dict[str, int]) -> np.ndarray:
    """ExG - Excess Green Index = 2G - R - B (normalizado 0-1 por canal)."""
    r = _get_band(arr, band_index, "R") / 255.0
    g = _get_band(arr, band_index, "G") / 255.0
    b = _get_band(arr, band_index, "B") / 255.0
    return 2 * g - r - b


def gli(arr: np.ndarray, band_index: Dict[str, int]) -> np.ndarray:
    """GLI - Green Leaf Index = (2G - R - B) / (2G + R + B)."""
    r = _get_band(arr, band_index, "R")
    g = _get_band(arr, band_index, "G")
    b = _get_band(arr, band_index, "B")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (2 * g - r - b) / (2 * g + r + b)
    out[~np.isfinite(out)] = np.nan
    return out


# Registro: qué índices están disponibles según las bandas del sensor.
# Cuando exista un sensor multiespectral, se añade aquí p.ej.:
#   "ndvi": {"requires": ["R", "NIR"], "func": ndvi_func}
INDEX_REGISTRY: Dict[str, dict] = {
    "vari": {"requires": ["R", "G", "B"], "func": vari,
             "label": "Índice de verdor (VARI, derivado de RGB)"},
    "exg": {"requires": ["R", "G", "B"], "func": exg,
            "label": "Excess Green (ExG)"},
    "gli": {"requires": ["R", "G", "B"], "func": gli,
            "label": "Green Leaf Index (GLI)"},
}

PRIMARY_INDEX = "vari"  # el que se usa para comunicación al usuario no técnico


def available_indices(sensor_bands: List[str]) -> List[str]:
    """Devuelve los índices calculables con las bandas disponibles."""
    available = []
    for name, spec in INDEX_REGISTRY.items():
        if all(b in sensor_bands for b in spec["requires"]):
            available.append(name)
    return available


def compute_index(name: str, arr: np.ndarray, sensor_bands: List[str]) -> np.ndarray:
    if name not in INDEX_REGISTRY:
        raise ValueError(f"Índice no registrado: {name}")
    spec = INDEX_REGISTRY[name]
    missing = [b for b in spec["requires"] if b not in sensor_bands]
    if missing:
        raise ValueError(
            f"No se puede calcular '{name}': faltan bandas {missing} "
            f"(sensor solo provee {sensor_bands})."
        )
    band_index = {b: i for i, b in enumerate(sensor_bands)}
    return spec["func"](arr, band_index)
