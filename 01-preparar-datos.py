"""Descarga las capas del área de estudio y las deja en `datos/<área>/`.

Uso
---
    uv run python 01-preparar-datos.py                    # Independencia
    uv run python 01-preparar-datos.py --area santiago    # Gran Santiago
    uv run python 01-preparar-datos.py --con-censo        # con zonas censales

Todo se descarga: las capas de OpenStreetMap salen de un extracto que baja
quackosm y las de contexto, de los datasets publicados por el curso de datos
geográficos. El resultado no depende de lo que haya en la máquina.

`--con-censo` agrega las zonas censales del Censo 2024. Va aparte porque la
cartografía se publica entera, con el país completo, y son 758 MB de descarga
para quedarse con las zonas de un área.

Salidas
-------
- `osm/limite.parquet`: polígonos comunales según OpenStreetMap.
- `osm/vias.parquet`: todas las ways con tag `highway` del área.
- `osm/lugares.parquet`: puntos de interés con nombre.
- `contexto/reclamos.parquet`: reportes SOSAFE del área.
- `contexto/zonas.parquet`: zonas censales, si la cartografía está disponible.
- `contexto/venues.parquet`: venues de Foursquare, si están.

El código pesado vive bajo `if __name__ == "__main__":` porque quackosm lanza
sus workers con el método de arranque "spawn": cada proceso hijo reimporta el
módulo principal y sin el guard reejecutaría la descarga completa.

Volver a correr el script no rehace lo ya descargado. Para forzar una
extracción nueva hay que borrar los parquet de `datos/<área>/osm/`.
"""

# %%
import time
from pathlib import Path

import geopandas as gpd

from redosm import config, contexto, descarga


def guardar(gdf: gpd.GeoDataFrame, ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(ruta)
    print(f"  {ruta}: {len(gdf)} filas, {ruta.stat().st_size / 1e6:.1f} MB")
    return ruta


# %%
if __name__ == "__main__":
    area = config.seleccionar()
    config.crear_directorios()
    inicio = time.perf_counter()

    print(f"Área de estudio: {area.titulo} ({len(area.comunas)} comunas)")
    print(f"Datos en {config.dir_datos()}")

    # --- Capas de OpenStreetMap ---------------------------------------
    ruta_limite = config.dir_osm() / "limite.parquet"
    if ruta_limite.exists():
        limite = gpd.read_parquet(ruta_limite)
        print(f"[1/5] Límite ya extraído: {ruta_limite}")
    else:
        print("[1/5] Extrayendo los límites comunales de OpenStreetMap")
        limite = descarga.limite_area(area)
        guardar(limite, ruta_limite)
    area_km2 = limite.to_crs(config.CRS_METRICO).area.sum() / 1e6
    print(f"  Superficie: {area_km2:.1f} km^2")

    ruta_vias = config.dir_osm() / "vias.parquet"
    if ruta_vias.exists():
        print(f"[2/5] Vías ya extraídas: {ruta_vias}")
    else:
        print("[2/5] Extrayendo las vías (highway=*)")
        guardar(descarga.vias(limite), ruta_vias)

    ruta_lugares = config.dir_osm() / "lugares.parquet"
    if ruta_lugares.exists():
        print(f"[3/5] Lugares ya extraídos: {ruta_lugares}")
    else:
        print("[3/5] Extrayendo los puntos de interés con nombre")
        guardar(descarga.lugares(limite), ruta_lugares)

    # --- Capas de contexto --------------------------------------------
    print("[4/5] Reportes SOSAFE")
    print(f"  Fuente: {config.resolver('sosafe')}")
    reclamos = contexto.cargar_reportes(limite)
    guardar(reclamos, config.dir_contexto() / "reclamos.parquet")
    print(reclamos["categoria"].value_counts().head(8).to_string())

    print("[5/5] Capas opcionales")
    zonas = contexto.cargar_zonas(limite)
    if zonas is None:
        print(
            "  Zonas censales: se omiten. Para incluirlas, correr con --con-censo"
            "\n  (descarga 758 MB de cartografía del Censo 2024)."
        )
    else:
        guardar(zonas, config.dir_contexto() / "zonas.parquet")
        print(f"  Población censada en el área: {int(zonas['n_per'].sum())}")

    venues = contexto.cargar_venues(limite)
    if venues is None:
        print("  Venues de Foursquare: fuente no disponible, se omite.")
    else:
        guardar(venues, config.dir_contexto() / "venues.parquet")
        print(f"  Check-ins asociados: {int(venues['checkins'].sum())}")

    print(f"\nPreparación terminada en {time.perf_counter() - inicio:.0f} s.")
