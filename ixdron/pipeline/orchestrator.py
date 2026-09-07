"""
IX DRON - pipeline.orchestrator

Punto 35: automatización máxima. Esta función es lo que ejecuta `ixdron process`
para UNA parcela: detecta vuelos nuevos, valida, calcula índices y
estadísticas, compara contra el vuelo anterior válido, actualiza el
histórico, y deja todo listo para que web_assets.py genere el dashboard.

No se sobreescribe ningún resultado existente salvo que se pida
explícitamente reprocesar (Punto 5 y 25).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import numpy as np

from ixdron.config import (
    IXDRON_PIPELINE_VERSION, DEFAULT_CHANGE_THRESHOLDS, DEFAULT_SENSOR_BANDS,
)
from ixdron.pipeline import ingestion, validation, raster_utils, indices as idx_mod
from ixdron.pipeline import statistics as stats_mod
from ixdron.pipeline import change_detection as change_mod
from ixdron.pipeline import rules as rules_mod
from ixdron.models.schemas import FlightMetadata


def load_parcel_config(parcel_path: Path) -> dict:
    cfg_file = parcel_path / "parcel_config.json"
    if cfg_file.exists():
        return json.loads(cfg_file.read_text())
    return {}


def load_history(parcel_path: Path) -> list:
    hist_file = parcel_path / "history" / "flights_index.json"
    if hist_file.exists():
        return json.loads(hist_file.read_text())
    return []


def save_history(parcel_path: Path, history: list) -> None:
    hist_dir = parcel_path / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    (hist_dir / "flights_index.json").write_text(
        json.dumps(history, indent=2, ensure_ascii=False)
    )


def upsert_history_record(history: list, record: dict) -> list:
    history = [r for r in history if r["flight_id"] != record["flight_id"]]
    history.append(record)
    return sorted(history, key=lambda r: r["date"])


def process_flight(flight_path: Path, parcel_path: Path, parcel_id: str,
                    client_id: str, force: bool = False) -> dict:
    """Procesa un único vuelo. Devuelve el registro histórico resultante."""
    property_boundary_path = parcel_path / "parcel_boundary.geojson"
    parcel_cfg = load_parcel_config(parcel_path)
    sensor_bands = parcel_cfg.get("sensor_bands", DEFAULT_SENSOR_BANDS)
    thresholds = {**DEFAULT_CHANGE_THRESHOLDS, **parcel_cfg.get("change_thresholds", {})}

    # Zona de análisis: por defecto es el predio completo (parcel_boundary),
    # pero si la parcela define una subzona (p. ej. solo la siembra, excluyendo
    # construcción/arbolado), TODO el cálculo de índices/estadísticas/cambios
    # se hace sobre esa subzona. parcel_boundary.geojson se conserva aparte
    # únicamente como referencia visual de contexto en el mapa.
    analysis_zone_file = parcel_cfg.get("analysis_zone_file")
    analysis_boundary_path = (parcel_path / analysis_zone_file) if analysis_zone_file \
        else property_boundary_path

    plant_counting_cfg = parcel_cfg.get("plant_counting", {})

    meta = ingestion.load_or_init_metadata(flight_path, parcel_id, client_id)

    if meta.status == "processed" and not force:
        # ya procesado con la misma versión: no reprocesar silenciosamente
        existing = flight_path / "analysis" / "stats.json"
        if existing.exists() and meta.pipeline_version == IXDRON_PIPELINE_VERSION:
            return json.loads(existing.read_text())

    v_boundary = validation.validate_parcel_boundary(analysis_boundary_path)
    if not v_boundary.ok:
        ingestion.mark_processed(flight_path, meta, "failed", "; ".join(v_boundary.errors))
        return {"flight_id": flight_path.name, "date": flight_path.name,
                "status": "failed", "errors": v_boundary.errors}

    ortho_path = ingestion.find_orthophoto(flight_path)
    v_ortho = validation.validate_orthophoto(ortho_path)
    if not v_ortho.ok:
        ingestion.mark_processed(flight_path, meta, "failed", "; ".join(v_ortho.errors))
        return {"flight_id": flight_path.name, "date": flight_path.name,
                "status": "failed", "errors": v_ortho.errors}

    v_overlap = validation.validate_geometry_overlap(ortho_path, analysis_boundary_path)
    if not v_overlap.ok:
        ingestion.mark_processed(flight_path, meta, "failed", "; ".join(v_overlap.errors))
        return {"flight_id": flight_path.name, "date": flight_path.name,
                "status": "failed", "errors": v_overlap.errors}

    analysis_dir = flight_path / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    try:
        bands, profile, bounds_4326 = raster_utils.load_rgb_masked(ortho_path, analysis_boundary_path)
    except Exception as e:  # noqa: BLE001
        error_msg = f"Error inesperado al recortar la ortofoto: {e}"
        ingestion.mark_processed(flight_path, meta, "failed", error_msg)
        return {"flight_id": flight_path.name, "date": flight_path.name,
                "status": "failed", "errors": [error_msg]}

    vari_array = idx_mod.compute_index("vari", bands, sensor_bands)

    # Además de VARI (el índice primario mostrado al usuario), se calculan
    # ExG y GLI para la sección educativa del modo técnico: así el usuario
    # curioso ve valores reales de su propia parcela, no solo teoría.
    indices_extra = {}
    for extra_name in ("exg", "gli"):
        try:
            arr = idx_mod.compute_index(extra_name, bands, sensor_bands)
            valid = arr[np.isfinite(arr)]
            if valid.size:
                indices_extra[extra_name] = {
                    "mean": float(np.mean(valid)),
                    "median": float(np.median(valid)),
                }
        except Exception:  # noqa: BLE001
            pass

    raster_utils.save_index_geotiff(vari_array, profile, analysis_dir / "vari.tif")
    raster_utils.array_to_web_png(bands, analysis_dir / "rgb_preview.png")
    vari_display_range = raster_utils.array_to_web_png(
        vari_array, analysis_dir / "vari_preview.png", cmap="vari"
    )

    stat = stats_mod.compute_statistics(
        vari_array, flight_path.name, meta.date, "vari"
    )

    # Área real de la zona de análisis, a partir de los píxeles válidos
    # (no del polígono dibujado, que puede incluir zonas fuera de la
    # cobertura real de la ortofoto).
    valid_px_count = int(np.isfinite(vari_array).sum())
    center_lat = (bounds_4326["miny"] + bounds_4326["maxy"]) / 2
    analysis_area_ha = raster_utils.compute_area_ha(profile, valid_px_count, center_lat)

    # Conteo estimado de plantas (opcional, punto 3): solo si la parcela lo
    # habilita explícitamente en parcel_config.json -> "plant_counting".
    plant_counting_result = None
    if plant_counting_cfg.get("enabled"):
        from ixdron.pipeline import plant_counting as pc_mod
        px_size_m = raster_utils.pixel_size_meters(profile, center_lat)
        plant_counting_result = pc_mod.estimate_plant_count(
            vari_array, px_size_m,
            expected_spacing_cm=plant_counting_cfg.get("expected_spacing_cm", 25.0),
            vari_threshold=plant_counting_cfg.get("vari_threshold", 0.10),
            smoothing_sigma_px=plant_counting_cfg.get("smoothing_sigma_px", 1.0),
        )

    history = load_history(parcel_path)
    from ixdron.pipeline.temporal import find_previous_valid_flight
    prev_record = find_previous_valid_flight(history, flight_path.name)

    change_summary = None
    recommendations = []
    warnings = list(v_ortho.warnings) + list(v_boundary.warnings)

    if prev_record is not None:
        prev_flight_path = flight_path.parent / prev_record["flight_id"]
        prev_vari_path = prev_flight_path / "analysis" / "vari.tif"
        prev_ortho = ingestion.find_orthophoto(prev_flight_path)

        v_comp = validation.check_comparability(ortho_path, prev_ortho) if prev_ortho else None
        if v_comp and not v_comp.ok:
            warnings.extend(v_comp.errors)
        elif prev_vari_path.exists():
            import rasterio
            with rasterio.open(prev_vari_path) as pv:
                prev_arr = pv.read(1)
                prev_profile = pv.profile.copy()
                prev_profile["crs"] = pv.crs
                prev_profile["transform"] = pv.transform

            aligned_current = raster_utils.align_to_reference(vari_array, profile, prev_profile)
            delta, change_record = change_mod.detect_change(
                aligned_current, prev_arr,
                flight_path.name, prev_record["flight_id"],
                "vari", thresholds["vari_delta_significant"],
            )
            raster_utils.array_to_web_png(delta, analysis_dir / "change_preview.png", cmap="change",
                                           vmin=-0.2, vmax=0.2)
            change_summary = change_record.__dict__
            recs = rules_mod.evaluate_rules(change_record, flight_path.name)
            recommendations = [r.__dict__ for r in recs]
            if v_comp:
                warnings.extend(v_comp.warnings)

    ingestion.mark_processed(flight_path, meta, "processed")

    record = {
        "flight_id": flight_path.name,
        "date": meta.date,
        "status": "baseline" if prev_record is None else "processed",
        "vari_mean": stat.mean,
        "vari_median": stat.median,
        "vari_display_range": list(vari_display_range) if vari_display_range else None,
        "change_display_range": [-0.2, 0.2],
        "vegetation_cover_pct": stat.vegetation_cover_pct,
        "valid_area_pct": stat.valid_area_pct,
        "analysis_area_ha": round(analysis_area_ha, 3) if analysis_area_ha else None,
        "used_analysis_zone_file": analysis_zone_file,
        "bounds_4326": bounds_4326,
        "change": change_summary,
        "recommendations": recommendations,
        "warnings": warnings,
        "pipeline_version": IXDRON_PIPELINE_VERSION,
        "indices_extra": indices_extra,
        "dsm_available": bool(meta.processing_params.get("dsm_available")) if meta.processing_params else False,
        "camera": meta.camera,
        "n_images": meta.n_images,
        "gsd_cm": meta.gsd_cm,
        "crs": meta.crs,
        "plant_counting": plant_counting_result,
    }

    (analysis_dir / "stats.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))

    history = upsert_history_record(history, record)
    save_history(parcel_path, history)

    return record


def process_parcel(parcel_path: Path, parcel_id: str, client_id: str,
                    force: bool = False) -> list:
    """Procesa todos los vuelos pendientes/nuevos de una parcela, en orden.

    Si la parcela tiene configurado `raw_flights_root` (carpeta con la
    salida cruda de ODM/WebODM, ver pipeline.odm_source), primero sincroniza
    los vuelos detectados ahí hacia la carpeta liviana `flights/` antes de
    procesarlos. Esto permite que el operador solo tenga que correr ODM y
    ejecutar `ixdron process`, sin ningún paso manual intermedio.
    """
    parcel_cfg = load_parcel_config(parcel_path)
    raw_root = parcel_cfg.get("raw_flights_root")
    if raw_root:
        from ixdron.pipeline import odm_source
        synced = odm_source.sync_flights_from_raw_root(
            parcel_path, Path(raw_root), parcel_id, client_id
        )
        print(f"  Sincronizados {len(synced)} vuelo(s) desde {raw_root}")

    results = []
    for flight_path in ingestion.discover_flights(parcel_path):
        try:
            results.append(process_flight(flight_path, parcel_path, parcel_id, client_id, force))
        except Exception as e:  # noqa: BLE001
            # Red de seguridad final: un error no anticipado en un vuelo
            # nunca debe detener el procesamiento de los demás vuelos ni de
            # otras parcelas en el mismo `ixdron process` (punto 26: nunca
            # generar un resultado falso, pero tampoco un corte total del
            # sistema por un solo vuelo problemático).
            print(f"  ERROR inesperado procesando {flight_path.name}: {e}")
            results.append({"flight_id": flight_path.name, "date": flight_path.name,
                             "status": "failed", "errors": [str(e)]})
    return results
