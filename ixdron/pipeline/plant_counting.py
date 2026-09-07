"""
IX DRON - pipeline.plant_counting

Estimación PRELIMINAR del número de plantas dentro de la zona de análisis,
a partir de máximos locales de un índice de vegetación (VARI).

Esto es deliberadamente una heurística de primera versión, no un modelo de
machine learning entrenado. Se documenta así en todos los lugares donde se
usa (código, JSON de salida, dashboard) porque el resultado alimenta un
cálculo de ingreso potencial del productor — nunca se presenta como un
conteo exacto.

Método:
  1. Suavizar levemente el índice (reduce ruido de textura de hoja/sombra).
  2. Quedarse solo con píxeles por encima de un umbral de vegetación
     (excluye suelo desnudo, sombras duras, construcciones).
  3. Encontrar máximos locales usando una ventana cuyo tamaño corresponde
     al espaciamiento esperado entre plantas (evita contar el mismo dosel
     varias veces).

Limitaciones conocidas (documentar siempre al usuario):
  - Sobreestima en etapas de traslape de dosel (canopy closure), donde
    varias plantas se funden en una sola mancha de verdor.
  - Subestima si la resolución (GSD) es gruesa respecto al tamaño de planta.
  - Sensible al umbral de vegetación y al espaciamiento configurado.
  - No distingue maleza de cultivo.
Precisión típica esperada en la literatura de conteo por imagen aérea para
maíz en etapas tempranas-medias: variable, del orden de 10-30% de error
frente a conteo manual, dependiendo de la etapa fenológica y el GSD.
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage


def estimate_plant_count(vari_array: np.ndarray, pixel_size_m: float,
                          expected_spacing_cm: float = 25.0,
                          vari_threshold: float = 0.10,
                          smoothing_sigma_px: float = 1.0) -> dict:
    """
    Devuelve un dict con el conteo estimado y los parámetros usados (para
    trazabilidad — Punto 5 de reproducibilidad: cualquier número debe poder
    rastrearse hasta el método y los parámetros que lo produjeron).
    """
    valid_mask = np.isfinite(vari_array)
    if not valid_mask.any():
        return {
            "plant_count_estimate": 0,
            "method": "heuristic_local_maxima_v1",
            "warning": "Sin píxeles válidos en la zona de análisis.",
        }

    filled = np.where(valid_mask, vari_array, -999.0)
    smoothed = ndimage.gaussian_filter(filled, sigma=smoothing_sigma_px)

    min_distance_px = max(1, int(round((expected_spacing_cm / 100.0) / pixel_size_m)))
    footprint_size = max(3, min_distance_px)  # ventana impar mínima razonable

    local_max = ndimage.maximum_filter(smoothed, size=footprint_size) == smoothed
    veg_mask = smoothed > vari_threshold

    peaks = local_max & veg_mask & valid_mask
    count = int(peaks.sum())

    return {
        "plant_count_estimate": count,
        "method": "heuristic_local_maxima_v1",
        "params": {
            "expected_spacing_cm": expected_spacing_cm,
            "vari_threshold": vari_threshold,
            "smoothing_sigma_px": smoothing_sigma_px,
            "min_distance_px": min_distance_px,
            "pixel_size_m_used": round(pixel_size_m, 4),
        },
        "confidence_note": (
            "Estimación preliminar por heurística de imagen, no un conteo "
            "exacto. Puede sobreestimar cuando el dosel se cierra entre "
            "plantas vecinas, y subestimar con resolución (GSD) gruesa. "
            "Se recomienda calibrar contra un conteo manual en al menos "
            "una zona de muestra antes de usarlo para decisiones."
        ),
    }
