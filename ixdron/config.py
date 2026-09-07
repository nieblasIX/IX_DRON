"""
IX DRON - Configuración global del sistema.

Centraliza rutas, versión del pipeline y parámetros por defecto.
No se debe hardcodear ninguna ruta fuera de este módulo.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Versión del pipeline (Punto 25 - Versionado)
# Cambiar solo cuando el algoritmo de índices/estadísticas cambie de forma
# que afecte la comparabilidad de resultados históricos.
# ---------------------------------------------------------------------------
IXDRON_PIPELINE_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CLIENTS_ROOT = DATA_ROOT / "clientes"
WEB_ROOT = PROJECT_ROOT / "web" / "dashboard"
WEB_DATA_ROOT = WEB_ROOT / "data"

# ---------------------------------------------------------------------------
# Parámetros por defecto de procesamiento
# Estos valores son el "config/rules.json" por defecto para una parcela que
# no define los suyos propios. Todo umbral debe poder sobreescribirse por
# parcela (ver models/schemas.py -> ParcelConfig).
# ---------------------------------------------------------------------------
DEFAULT_CHANGE_THRESHOLDS = {
    # Diferencia mínima de VARI (valor absoluto) para considerar que un
    # píxel cambió de forma "significativa" y no es ruido de iluminación /
    # radiometría entre vuelos.
    "vari_delta_significant": 0.03,
    # Por encima de este delta positivo/negativo se clasifica como
    # incremento/disminución; entre -significant y +significant es "estable".
}

DEFAULT_WEB_PREVIEW_MAX_PIXELS = 2000  # lado máximo del preview PNG para web
DEFAULT_COG_SIZE_THRESHOLD_MB = 200  # a partir de aquí, generar COG/tiles

# Sensor por defecto asumido en esta versión. Ver pipeline/indices.py para
# el registro sensor -> índices disponibles.
DEFAULT_SENSOR_BANDS = ["R", "G", "B"]

SUPPORTED_ORTHO_EXTENSIONS = (".tif", ".tiff")
