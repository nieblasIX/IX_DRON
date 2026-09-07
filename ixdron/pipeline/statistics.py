"""
IX DRON - pipeline.statistics

Calcula estadísticas descriptivas de un índice para un vuelo. El esquema de
salida (StatisticRecord) tiene un campo `extra` abierto para no limitar
futuros indicadores (Punto 11: no limitar el esquema a los campos iniciales).
"""
from __future__ import annotations
import numpy as np

from ixdron.models.schemas import StatisticRecord


def compute_statistics(index_array: np.ndarray, flight_id: str, date: str,
                        index_name: str, vegetation_threshold: float = 0.05
                        ) -> StatisticRecord:
    valid = index_array[np.isfinite(index_array)]
    total_px = index_array.size
    valid_px = valid.size

    if valid_px == 0:
        return StatisticRecord(
            flight_id=flight_id, date=date, index_name=index_name,
            extra={"warning": "Sin píxeles válidos dentro de la parcela."},
        )

    vegetation_cover_pct = float(np.sum(valid > vegetation_threshold) / valid_px * 100)

    return StatisticRecord(
        flight_id=flight_id,
        date=date,
        index_name=index_name,
        mean=float(np.mean(valid)),
        median=float(np.median(valid)),
        std=float(np.std(valid)),
        p10=float(np.percentile(valid, 10)),
        p90=float(np.percentile(valid, 90)),
        vegetation_cover_pct=vegetation_cover_pct,
        valid_area_pct=float(valid_px / total_px * 100),
    )
