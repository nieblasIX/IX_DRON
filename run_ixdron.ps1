# run_ixdron.ps1
#
# Lanzador de IX DRON para Windows. Existe porque en máquinas con
# PostgreSQL/PostGIS instalado, el instalador suele dejar configuradas las
# variables de entorno PROJ_LIB / PROJ_DATA apuntando a SU PROPIO proj.db,
# de una versión distinta a la que trae rasterio. Eso hace que rasterio
# falle con errores como:
#
#   "The EPSG code is unknown. PROJ: ... DATABASE.LAYOUT.VERSION.MINOR = 2
#    whereas a number >= 6 is expected. It comes from another PROJ installation."
#
# Este script limpia esas variables SOLO para este proceso (no toca la
# configuración del sistema ni afecta a PostGIS), activa el entorno virtual,
# y corre el comando de ixdron que le pases.
#
# Uso:
#   .\run_ixdron.ps1 process
#   .\run_ixdron.ps1 process --force
#   .\run_ixdron.ps1 list
#   .\run_ixdron.ps1 build

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

# --- Ajusta esta ruta si tu .venv vive en otro lugar ---
$VenvActivate = "$PSScriptRoot\..\SAN_AGUSTIN_ZAPOTLAN\.venv\Scripts\Activate.ps1"

if (Test-Path $VenvActivate) {
    & $VenvActivate
} else {
    Write-Warning "No se encontró el entorno virtual en $VenvActivate. Continuando con el Python activo en esta terminal."
}

# Elimina el conflicto PROJ_LIB/PROJ_DATA heredado de PostGIS, solo para
# este proceso.
Remove-Item Env:PROJ_LIB  -ErrorAction SilentlyContinue
Remove-Item Env:PROJ_DATA -ErrorAction SilentlyContinue

$env:PYTHONPATH = "$PSScriptRoot"

if (-not $Args -or $Args.Count -eq 0) {
    $Args = @("process")
}

python -m ixdron.cli @Args
