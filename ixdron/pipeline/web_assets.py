"""
IX DRON - pipeline.web_assets

Genera los JSON estáticos que consume el dashboard (Leaflet + Plotly) y
copia los previews de imagen a la carpeta web pública. Este es el ÚNICO
módulo que escribe dentro de /web/dashboard/data — el operador nunca debe
tocar esos archivos a mano.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path

from ixdron.pipeline.orchestrator import load_history, load_parcel_config
from ixdron.pipeline import temporal


def build_parcel_dashboard_data(parcel_path: Path, parcel_id: str,
                                 client_id: str, web_data_root: Path) -> None:
    history = load_history(parcel_path)
    parcel_cfg = load_parcel_config(parcel_path)

    out_dir = web_data_root / client_id / parcel_id
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = out_dir / "previews"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Copiar el polígono del predio completo (contexto visual en el mapa)
    boundary_src = parcel_path / "parcel_boundary.geojson"
    if boundary_src.exists():
        shutil.copy(boundary_src, out_dir / "parcel_boundary.geojson")

    # Copiar el polígono de la zona de análisis, si es distinto al predio
    # completo (p. ej. solo la siembra, excluyendo construcción/arbolado).
    # El dashboard dibuja ambos límites con estilos distintos quan difieren.
    analysis_zone_file = parcel_cfg.get("analysis_zone_file")
    has_separate_zone = False
    if analysis_zone_file:
        zone_src = parcel_path / analysis_zone_file
        if zone_src.exists():
            shutil.copy(zone_src, out_dir / "analysis_zone.geojson")
            has_separate_zone = True

    # Copiar previews de cada vuelo procesado
    enriched_history = []
    for record in history:
        record = dict(record)
        flight_dir = parcel_path / "flights" / record["flight_id"] / "analysis"
        rel_previews = {}
        for name, fname in (("rgb", "rgb_preview.png"),
                             ("vari", "vari_preview.png"),
                             ("change", "change_preview.png")):
            src = flight_dir / fname
            if src.exists():
                dst_name = f"{record['flight_id']}_{fname}"
                shutil.copy(src, assets_dir / dst_name)
                rel_previews[name] = f"previews/{dst_name}"
        record["previews"] = rel_previews
        enriched_history.append(record)

    timeseries = temporal.build_timeseries(enriched_history)
    monthly = temporal.monthly_summary(enriched_history)
    yearly = temporal.yearly_summary(enriched_history)
    maturity = temporal.data_maturity_level(len(enriched_history), enriched_history)

    dashboard_payload = {
        "client_id": client_id,
        "parcel_id": parcel_id,
        "parcel_name": parcel_cfg.get("name", parcel_id),
        "use_case": parcel_cfg.get("use_case", "agriculture"),
        "data_maturity": maturity,
        "n_flights": len(enriched_history),
        "has_separate_analysis_zone": has_separate_zone,
        "flights": timeseries,
        "monthly_summary": monthly,
        "yearly_summary": yearly,
        "latest": timeseries[-1] if timeseries else None,
    }

    (out_dir / "dashboard.json").write_text(
        json.dumps(dashboard_payload, indent=2, ensure_ascii=False)
    )


def build_project_index(web_data_root: Path, entries: list[dict]) -> None:
    """
    Índice global (para soportar multi-parcela/multi-cliente desde el MVP,
    Punto 21/31): lista qué parcelas tienen dashboard disponible.
    """
    (web_data_root / "projects_index.json").write_text(
        json.dumps(entries, indent=2, ensure_ascii=False)
    )
