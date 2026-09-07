"""
Genera datos de demostración para IX DRON:
  - 1 parcela con geometría (parcel_boundary.geojson)
  - 3 vuelos con "ortofotos" GeoTIFF sintéticas RGB (simulan un ODM output)
    con un patrón de vegetación que decrece levemente en la zona oeste en el
    tercer vuelo, para poder ver el motor de reglas / detección de cambios
    funcionando con datos no triviales.

Esto reemplaza fotografías reales de dron, que no están disponibles en este
entorno. En producción, estos archivos vendrían de WebODM.
"""
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parent.parent
PARCEL_PATH = ROOT / "data" / "clientes" / "CLIENTE_DEMO" / "parcelas" / "PARCELA_DEMO"

WIDTH, HEIGHT = 400, 300
PIXEL_SIZE = 0.05  # 5 cm/px, GSD típico de dron
# Ubicación de ejemplo: Valle de Toluca, México (arbitraria para la demo)
ORIGIN_LON, ORIGIN_LAT = -99.6300, 19.2900
CRS = "EPSG:4326"  # simplificado para la demo (idealmente sería UTM)


def make_parcel_boundary():
    # Rectángulo que cubre aproximadamente el raster generado
    dlon = WIDTH * PIXEL_SIZE / 111000  # aprox grados
    dlat = HEIGHT * PIXEL_SIZE / 111000
    minx, miny = ORIGIN_LON, ORIGIN_LAT - dlat
    maxx, maxy = ORIGIN_LON + dlon, ORIGIN_LAT
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "PARCELA_DEMO"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]
                ]]
            }
        }]
    }
    PARCEL_PATH.mkdir(parents=True, exist_ok=True)
    (PARCEL_PATH / "parcel_boundary.geojson").write_text(json.dumps(geojson, indent=2))
    print("parcel_boundary.geojson creado")


def make_parcel_config():
    cfg = {
        "parcel_id": "PARCELA_DEMO",
        "client_id": "CLIENTE_DEMO",
        "name": "Parcela Demo - Cultivo de prueba",
        "use_case": "agriculture",
        "sensor_bands": ["R", "G", "B"],
        "change_thresholds": {"vari_delta_significant": 0.03},
    }
    (PARCEL_PATH / "parcel_config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    print("parcel_config.json creado")


def synth_orthophoto(seed: int, decline_west: float = 0.0) -> np.ndarray:
    """
    Genera una imagen RGB sintética [3,H,W] uint8 simulando vegetación:
    más "verde" (G alto) en general, con textura de ruido, y un decline
    opcional en la mitad oeste (para simular estrés hídrico/manejo).
    """
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:HEIGHT, 0:WIDTH]

    base_green = 140 + 20 * np.sin(x / 30) + 15 * np.cos(y / 25)
    noise = rng.normal(0, 8, (HEIGHT, WIDTH))
    green = base_green + noise

    # decline en la mitad oeste (x < WIDTH/2)
    west_mask = x < (WIDTH / 2)
    green = green - west_mask * decline_west

    red = 90 + rng.normal(0, 6, (HEIGHT, WIDTH))
    blue = 70 + rng.normal(0, 5, (HEIGHT, WIDTH))

    rgb = np.stack([red, green, blue])
    rgb = np.clip(rgb, 0, 255).astype("uint8")
    return rgb


def write_geotiff(rgb: np.ndarray, out_path: Path):
    transform = from_origin(ORIGIN_LON, ORIGIN_LAT, PIXEL_SIZE / 111000, PIXEL_SIZE / 111000)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, "w", driver="GTiff",
        height=rgb.shape[1], width=rgb.shape[2], count=3, dtype="uint8",
        crs=CRS, transform=transform,
    ) as dst:
        dst.write(rgb)


def make_flight(flight_id: str, decline_west: float, seed: int):
    flight_dir = PARCEL_PATH / "flights" / flight_id
    products_dir = flight_dir / "odm" / "products"
    rgb = synth_orthophoto(seed=seed, decline_west=decline_west)
    write_geotiff(rgb, products_dir / "odm_orthophoto.tif")

    metadata = {
        "flight_id": flight_id,
        "parcel_id": "PARCELA_DEMO",
        "client_id": "CLIENTE_DEMO",
        "date": flight_id,
        "time": "10:30",
        "altitude_m": 80,
        "gsd_cm": 5.0,
        "camera": "DJI Mavic 3M (demo sintético)",
        "n_images": 145,
        "resolution": "5280x3956",
        "crs": CRS,
        "coverage_pct": 98.5,
        "processing_params": {"note": "datos sintéticos de demostración"},
        "status": "pending",
    }
    (flight_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"Vuelo sintético creado: {flight_id}")


if __name__ == "__main__":
    make_parcel_boundary()
    make_parcel_config()
    # Vuelo 1: baseline. Vuelo 2: leve decline oeste. Vuelo 3: decline mayor
    # (simula progresión de estrés en zona oeste, detectable por el motor de reglas)
    make_flight("2026-08-01", decline_west=0, seed=1)
    make_flight("2026-08-15", decline_west=10, seed=2)
    make_flight("2026-08-29", decline_west=35, seed=3)
    print("\nDatos de demo generados en:", PARCEL_PATH)
