"""
IX DRON - CLI

Punto 28: el operador idealmente solo necesita `ixdron process`.
Uso:
    python -m ixdron.cli process [--client CLIENTE_ID] [--parcel PARCELA_ID] [--force]
    python -m ixdron.cli build    # regenera solo los assets web sin reprocesar
    python -m ixdron.cli list     # lista clientes/parcelas/vuelos detectados
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from ixdron.config import CLIENTS_ROOT, WEB_DATA_ROOT
from ixdron.pipeline import orchestrator, web_assets


def iter_parcels():
    if not CLIENTS_ROOT.exists():
        return
    for client_dir in sorted(CLIENTS_ROOT.iterdir()):
        if not client_dir.is_dir():
            continue
        parcels_dir = client_dir / "parcelas"
        if not parcels_dir.exists():
            continue
        for parcel_dir in sorted(parcels_dir.iterdir()):
            if parcel_dir.is_dir():
                yield client_dir.name, parcel_dir.name, parcel_dir


def cmd_process(args):
    processed_any = False
    index_entries = []
    for client_id, parcel_id, parcel_path in iter_parcels():
        if args.client and client_id != args.client:
            continue
        if args.parcel and parcel_id != args.parcel:
            continue
        print(f"\n=== Procesando {client_id}/{parcel_id} ===")
        try:
            results = orchestrator.process_parcel(parcel_path, parcel_id, client_id, force=args.force)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR inesperado procesando la parcela: {e}")
            continue
        for r in results:
            status = r.get("status")
            print(f"  vuelo {r['flight_id']}: {status}")
            if status == "failed":
                for e in r.get("errors", []):
                    print(f"     ERROR: {e}")
        web_assets.build_parcel_dashboard_data(parcel_path, parcel_id, client_id, WEB_DATA_ROOT)
        index_entries.append({"client_id": client_id, "parcel_id": parcel_id,
                               "n_flights": len(results)})
        processed_any = True

    web_assets.build_project_index(WEB_DATA_ROOT, index_entries)
    if not processed_any:
        print("No se encontraron parcelas para procesar. Revisa data/clientes/.")
    else:
        print("\nListo. Dashboard actualizado en web/dashboard/.")


def cmd_build(args):
    index_entries = []
    for client_id, parcel_id, parcel_path in iter_parcels():
        web_assets.build_parcel_dashboard_data(parcel_path, parcel_id, client_id, WEB_DATA_ROOT)
        index_entries.append({"client_id": client_id, "parcel_id": parcel_id})
    web_assets.build_project_index(WEB_DATA_ROOT, index_entries)
    print("Assets web regenerados sin reprocesar vuelos.")


def cmd_list(args):
    for client_id, parcel_id, parcel_path in iter_parcels():
        flights = sorted((parcel_path / "flights").iterdir()) if (parcel_path / "flights").exists() else []
        print(f"{client_id}/{parcel_id}: {len(flights)} vuelo(s)")
        for f in flights:
            meta_file = f / "metadata.json"
            status = "?"
            if meta_file.exists():
                status = json.loads(meta_file.read_text()).get("status", "?")
            print(f"   - {f.name} [{status}]")


def main():
    parser = argparse.ArgumentParser(prog="ixdron")
    sub = parser.add_subparsers(dest="command", required=True)

    p_process = sub.add_parser("process", help="Procesa vuelos nuevos y actualiza el dashboard")
    p_process.add_argument("--client", help="Procesar solo este cliente")
    p_process.add_argument("--parcel", help="Procesar solo esta parcela")
    p_process.add_argument("--force", action="store_true", help="Reprocesar aunque ya exista resultado")
    p_process.set_defaults(func=cmd_process)

    p_build = sub.add_parser("build", help="Regenera solo los JSON del dashboard")
    p_build.set_defaults(func=cmd_build)

    p_list = sub.add_parser("list", help="Lista clientes/parcelas/vuelos")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
