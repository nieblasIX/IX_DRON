# Uso operativo

Esta guía está pensada para la persona que vuela el dron, no para quien
programó el sistema.

## Flujo de un vuelo nuevo

1. **Volar** el dron siguiendo el protocolo de vuelo de la parcela
   (altitud, traslape, patrón de vuelo constantes entre vuelos para que
   sean comparables).
2. **Procesar en WebODM/ODM** las fotografías descargadas, para obtener
   el ortomosaico (`orthophoto.tif`).
3. **Colocar el resultado** en:
   ```
   data/clientes/{CLIENTE}/parcelas/{PARCELA}/flights/{AAAA-MM-DD}/odm/products/odm_orthophoto.tif
   ```
   El nombre de la carpeta del vuelo **debe ser la fecha en formato
   `AAAA-MM-DD`** (es la convención que usa el sistema para ordenar y
   comparar vuelos).
4. **Ejecutar:**
   ```bash
   PYTHONPATH=. python3 -m ixdron.cli process
   ```
5. Revisar la salida en consola: dirá `baseline` (primer vuelo),
   `processed` (comparado exitosamente) o `failed` (con el motivo).
6. Publicar (`git push` de `web/dashboard/`, ver `docs/INSTALL.md`).
7. El cliente abre el mismo enlace de siempre — no hay nada más que
   compartir ni configurar por vuelo.

No es necesario editar ningún HTML, JavaScript o JSON manualmente en
ningún paso de este flujo.

## Comandos disponibles

```bash
ixdron process                 # procesa todos los vuelos nuevos de todas las parcelas
ixdron process --client X      # solo los vuelos de un cliente
ixdron process --parcel Y      # solo los vuelos de una parcela
ixdron process --force         # reprocesa incluso vuelos ya procesados
ixdron build                   # regenera solo los JSON del dashboard, sin reprocesar
ixdron list                    # lista clientes/parcelas/vuelos y su estado
```
(Ejecutar siempre con `PYTHONPATH=.` desde la raíz del proyecto, o instalar
el paquete con `pip install -e .` — ver nota en `docs/INSTALL.md` si se
desea empaquetar formalmente.)

## Qué hacer si un vuelo falla

El comando imprime el motivo (por ejemplo: "no se encontró ortofoto",
"el raster no tiene CRS definido", "los vuelos no se solapan
espacialmente"). El vuelo queda marcado `failed` en su `metadata.json` y
**no se usa** como referencia para el siguiente vuelo — el sistema
automáticamente comparará el próximo vuelo válido contra el último vuelo
válido anterior, saltándose el fallido.

## Conectar vuelos reales de ODM/WebODM (sin reorganizar tus carpetas)

IX DRON puede leer directamente la estructura que deja una corrida de
ODM/WebODM en disco — no hace falta copiar ni renombrar nada. Ejemplo real:

```
SAN_AGUSTIN_ZAPOTLAN/                    <- una carpeta por parcela
  SAZ_JOSE_2026_09_03/                   <- una carpeta por vuelo (nombre libre + fecha)
    SAZ_JOSE/                            <- carpeta de proyecto que crea ODM
      odm_orthophoto/odm_orthophoto.tif
      odm_dem/dsm.tif
      cameras.json, options.json, log.json, images/...
```

Para conectar esta carpeta a una parcela de IX DRON, agrega en su
`parcel_config.json`:

```json
{
  "parcel_id": "JOSE",
  "client_id": "SAN_AGUSTIN_ZAPOTLAN",
  "name": "Parcela de José",
  "raw_flights_root": "C:/Users/Lenovo/Documents/IX_DRON/SAN_AGUSTIN_ZAPOTLAN"
}
```

(En Windows, usar barras `/` dentro del JSON — Python las acepta igual que
`\\`, y así se evita tener que escapar cada backslash.)

A partir de ahí, `ixdron process` hace todo automáticamente:

1. Recorre `raw_flights_root` buscando subcarpetas de vuelo.
2. Extrae la fecha del nombre de la carpeta (reconoce `_2026_09_03`,
   `2026-09-03`, `20260903`, sin importar qué prefijo la acompañe).
3. Localiza `odm_orthophoto/odm_orthophoto.tif` y `odm_dem/dsm.tif` dentro
   del proyecto ODM (sin importar si ODM corrió directamente en la carpeta
   del vuelo o en una subcarpeta de proyecto).
4. Lee cámara (`cameras.json`), número de imágenes (carpeta `images/`),
   parámetros de procesamiento (`options.json`) y calcula el GSD real a
   partir del propio GeoTIFF (más confiable que cualquier valor reportado
   en los JSON de ODM).
5. Guarda en `flights/{fecha}/source.json` la ruta absoluta al proyecto
   ODM real, para trazabilidad — el GeoTIFF **nunca se copia ni se mueve**.

Si una carpeta de vuelo no tiene una fecha reconocible en su nombre, se
omite con un aviso en consola (no rompe el resto del procesamiento).

Este mecanismo convive con el flujo original (colocar manualmente el
ortomosaico en `flights/{fecha}/odm/products/`): si no se configura
`raw_flights_root`, IX DRON sigue buscando ahí, como en el MVP inicial.


`parcel_config.json` dentro de la carpeta de la parcela:

```json
{
  "parcel_id": "PARCELA_DEMO",
  "client_id": "CLIENTE_DEMO",
  "name": "Nombre visible en el dashboard",
  "use_case": "agriculture",
  "sensor_bands": ["R", "G", "B"],
  "change_thresholds": { "vari_delta_significant": 0.03 }
}
```

- `sensor_bands`: cuando en el futuro se incorpore un sensor
  multiespectral, se declara aquí (p. ej. `["R","G","B","NIR"]`) y el
  sistema habilita automáticamente los índices que esas bandas permiten
  calcular (ver `pipeline/indices.py`).
- `change_thresholds.vari_delta_significant`: qué tan grande debe ser un
  cambio de VARI entre vuelos para clasificarse como incremento/disminución
  en vez de "estable". Ajustar con el historial de la parcela si se
  observan demasiados falsos positivos.

## Cómo evoluciona el dashboard según los datos disponibles

No hay que configurar nada para esto — ocurre automáticamente:

- **1 vuelo:** el dashboard muestra "vuelo de referencia".
- **2 vuelos:** aparece la comparación y el mapa de cambio.
- **3+ vuelos:** aparece la serie temporal.
- **Datos de 2+ años calendario:** se habilita (a nivel de datos, en
  `dashboard.json → yearly_summary`) la comparación interanual.

## Interpretar el modo técnico

El botón "Modo técnico" del dashboard muestra, para auditoría: VARI media
y mediana, porcentaje de área válida, versión del pipeline usada en cada
vuelo, y las advertencias registradas por el módulo de validación (por
ejemplo, diferencias de resolución entre vuelos). Si algo se ve raro en
el modo simple ("Parcela"), el modo técnico es el primer lugar donde
buscar la explicación.
