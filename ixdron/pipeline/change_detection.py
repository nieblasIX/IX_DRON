"""
IX DRON - pipeline.change_detection

Compara el índice del vuelo actual contra el vuelo anterior VÁLIDO
(ignorando vuelos marcados como 'failed'). Los umbrales de clasificación
son configurables y se registran junto al resultado (Punto 10).
"""
from __future__ import annotations
import numpy as np

from ixdron.models.schemas import ChangeDetectionRecord


def detect_change(current: np.ndarray, previous: np.ndarray,
                   flight_id_current: str, flight_id_previous: str,
                   index_name: str, threshold: float,
                   comparison_type: str = "sequential"
                   ) -> tuple[np.ndarray, ChangeDetectionRecord]:
    """
    `current` y `previous` deben venir ya alineados a la misma rejilla
    (ver raster_utils.align_to_reference). Devuelve (delta_array, record).
    """
    delta = current - previous
    valid = np.isfinite(delta)
    warnings = []

    if not valid.any():
        warnings.append("No hay píxeles válidos comunes entre ambos vuelos.")

    valid_delta = delta[valid]
    total_valid = valid_delta.size

    if total_valid > 0:
        pct_increase = float(np.sum(valid_delta > threshold) / total_valid * 100)
        pct_decrease = float(np.sum(valid_delta < -threshold) / total_valid * 100)
        pct_stable = 100.0 - pct_increase - pct_decrease
        mean_delta = float(np.mean(valid_delta))
    else:
        pct_increase = pct_decrease = pct_stable = mean_delta = None

    record = ChangeDetectionRecord(
        flight_id_current=flight_id_current,
        flight_id_previous=flight_id_previous,
        comparison_type=comparison_type,
        index_name=index_name,
        mean_delta=mean_delta,
        pct_area_increase=pct_increase,
        pct_area_stable=pct_stable,
        pct_area_decrease=pct_decrease,
        threshold_used=threshold,
        warnings=warnings,
    )
    return delta, record
