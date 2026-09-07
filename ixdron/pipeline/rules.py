"""
IX DRON - pipeline.rules

Motor de reglas configurable (Punto 20). Cada regla evalúa el resultado de
change_detection y produce, si aplica, un Recommendation con tres campos
SIEMPRE separados: observation / interpretation / recommendation.

Las reglas se definen como datos (lista de dicts) para poder moverlas a un
config/rules.json editable por caso de uso sin tocar código.
"""
from __future__ import annotations
from typing import List, Dict, Any

from ixdron.models.schemas import ChangeDetectionRecord, Recommendation

DEFAULT_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "significant_decrease_concentrated",
        "condition": lambda c: c.pct_area_decrease is not None and c.pct_area_decrease > 15,
        "observation": lambda c: (
            f"Se detectó disminución del índice de verdor (VARI) en aproximadamente "
            f"{c.pct_area_decrease:.1f}% del área analizada respecto al vuelo anterior."
        ),
        "interpretation": (
            "Este cambio puede corresponder a variación de cobertura vegetal, "
            "condiciones de iluminación al momento del vuelo, manejo agronómico "
            "reciente u otras causas no distinguibles únicamente con imágenes RGB."
        ),
        "recommendation": "Se recomienda inspección de campo en las zonas señaladas para determinar la causa.",
        "severity": "attention",
    },
    {
        "rule_id": "significant_increase_widespread",
        "condition": lambda c: c.pct_area_increase is not None and c.pct_area_increase > 30,
        "observation": lambda c: (
            f"Se detectó incremento del índice de verdor en aproximadamente "
            f"{c.pct_area_increase:.1f}% del área analizada."
        ),
        "interpretation": (
            "Un incremento amplio suele asociarse a crecimiento vegetativo o "
            "respuesta favorable tras riego/lluvia, aunque también puede reflejar "
            "cambios de iluminación entre vuelos."
        ),
        "recommendation": "Continuar el monitoreo regular; no se requiere acción inmediata.",
        "severity": "info",
    },
    {
        "rule_id": "stable",
        "condition": lambda c: (
            c.pct_area_stable is not None and c.pct_area_stable > 80
        ),
        "observation": lambda c: (
            f"El {c.pct_area_stable:.1f}% del área se mantuvo estable respecto al vuelo anterior."
        ),
        "interpretation": "No se identifican cambios relevantes en el periodo evaluado.",
        "recommendation": "Mantener la frecuencia de monitoreo actual.",
        "severity": "info",
    },
]


def evaluate_rules(change: ChangeDetectionRecord, flight_id: str,
                    rules: List[Dict[str, Any]] = None) -> List[Recommendation]:
    rules = rules or DEFAULT_RULES
    results = []
    for rule in rules:
        try:
            if rule["condition"](change):
                obs = rule["observation"](change) if callable(rule["observation"]) else rule["observation"]
                results.append(Recommendation(
                    flight_id=flight_id,
                    rule_id=rule["rule_id"],
                    observation=obs,
                    interpretation=rule["interpretation"],
                    recommendation=rule["recommendation"],
                    severity=rule.get("severity", "info"),
                ))
        except Exception:  # noqa: BLE001
            continue
    return results
