"""
IX DRON - pipeline.temporal

Punto 37: la fecha es una dimensión fundamental. Este módulo NUNCA lee ni
escribe archivos por año (2026.json, 2027.json...). Toda vista temporal
(semana/mes/trimestre/año/histórico) se DERIVA en memoria a partir de la
lista `flights[]` guardada en history/flights_index.json.

Funciones puras: reciben una lista de registros históricos y devuelven
agregaciones. Así funcionan igual con 2 o con 500 vuelos.
"""
from __future__ import annotations
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any


def _parse_date(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


def build_timeseries(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serie temporal simple, ordenada por fecha, tal cual la consume Plotly."""
    return sorted(history, key=lambda r: r["date"])


def monthly_summary(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Agrupa vuelos por año-mes y calcula un resumen (Punto 13/23).
    No requiere que existan meses completos ni intervalos regulares.
    """
    buckets: Dict[str, list] = defaultdict(list)
    for r in history:
        dt = _parse_date(r["date"])
        key = f"{dt.year:04d}-{dt.month:02d}"
        buckets[key].append(r)

    summaries = []
    sorted_keys = sorted(buckets.keys())
    for i, key in enumerate(sorted_keys):
        flights = sorted(buckets[key], key=lambda r: r["date"])
        means = [f["vari_mean"] for f in flights if f.get("vari_mean") is not None]
        summary = {
            "period": key,
            "n_flights": len(flights),
            "vari_mean_avg": sum(means) / len(means) if means else None,
            "first_date": flights[0]["date"],
            "last_date": flights[-1]["date"],
        }
        # comparación contra el mes anterior en la lista (si existe)
        if i > 0:
            prev = summaries[i - 1]
            if summary["vari_mean_avg"] is not None and prev["vari_mean_avg"] is not None:
                summary["delta_vs_previous_month"] = round(
                    summary["vari_mean_avg"] - prev["vari_mean_avg"], 4
                )
        summaries.append(summary)
    return summaries


def yearly_summary(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Agrupa por año. Base para navegación [2026][2027][2028][TODO] (Punto 24)."""
    buckets: Dict[int, list] = defaultdict(list)
    for r in history:
        buckets[_parse_date(r["date"]).year].append(r)

    summaries = []
    for year in sorted(buckets.keys()):
        flights = buckets[year]
        means = [f["vari_mean"] for f in flights if f.get("vari_mean") is not None]
        summaries.append({
            "year": year,
            "n_flights": len(flights),
            "vari_mean_avg": sum(means) / len(means) if means else None,
        })
    return summaries


def find_previous_valid_flight(history: List[Dict[str, Any]], current_id: str
                                ) -> Dict[str, Any] | None:
    """
    Busca el vuelo inmediatamente anterior (por fecha) que NO esté 'failed'.

    Funciona tanto si `current_id` ya existe en `history` (reprocesamiento)
    como si todavía no se ha insertado (caso normal: se busca el anterior
    ANTES de guardar el registro del vuelo que se está procesando).
    """
    if not history:
        return None

    # Determinar la fecha de referencia del vuelo actual: si ya está en el
    # histórico se usa su fecha registrada; si no, se asume que flight_id
    # es la fecha (convención del sistema: nombre de carpeta = fecha ISO).
    current_record = next((r for r in history if r["flight_id"] == current_id), None)
    current_date = current_record["date"] if current_record else current_id

    candidates = [
        r for r in history
        if r["flight_id"] != current_id
        and r["date"] < current_date
        and r.get("status") != "failed"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r["date"])


def find_same_period_last_year(history: List[Dict[str, Any]], current_date: str
                                ) -> Dict[str, Any] | None:
    """
    Punto 15: busca un vuelo del mismo mes, un año antes, para habilitar la
    comparación interanual (distinta de la comparación secuencial reciente).
    """
    dt = _parse_date(current_date)
    target_year = dt.year - 1
    candidates = [
        r for r in history
        if _parse_date(r["date"]).year == target_year
        and _parse_date(r["date"]).month == dt.month
        and r.get("status") != "failed"
    ]
    if not candidates:
        return None
    # el más cercano en día al vuelo actual
    candidates.sort(key=lambda r: abs((_parse_date(r["date"]) - dt.replace(year=target_year)).days))
    return candidates[0]


def data_maturity_level(n_flights: int, history: List[Dict[str, Any]]) -> str:
    """
    Punto 36: la interfaz debe evolucionar automáticamente según cuántos
    datos existen. Devuelve el nivel de madurez para que el dashboard decida
    qué bloques mostrar.
    """
    if n_flights <= 0:
        return "empty"
    if n_flights == 1:
        return "baseline"
    if n_flights == 2:
        return "comparison"
    years_present = {_parse_date(r["date"]).year for r in history}
    if len(years_present) >= 2:
        return "interannual"
    return "timeseries"
