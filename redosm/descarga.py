"""Extracción de OpenStreetMap con quackosm y descarga de datasets del curso.

quackosm baja un extracto PBF de la zona (via BBBike o Geofabrik), lo lee con
DuckDB y devuelve un GeoDataFrame. Sus workers usan `multiprocessing` con
método de arranque "spawn", así que el código que llame a estas funciones debe
quedar dentro de `if __name__ == "__main__":`. Si no, cada proceso hijo
reejecuta el script completo.
"""

from __future__ import annotations

import multiprocessing as mp
import tarfile
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
import quackosm as qosm
from shapely.geometry import box

from redosm import config

# Atributos que se conservan de cada way vial. OSM pública cientos de tags;
# estos son los que usan las reglas de acceso por modo y el grafo exportado.
ATRIBUTOS_VIA = [
    "highway",
    "name",
    "alt_name",
    "oneway",
    "maxspeed",
    "surface",
    "lanes",
    "lit",
    "bridge",
    "tunnel",
    "layer",
    "access",
    "service",
    "bicycle",
    "foot",
    "motor_vehicle",
    "motorcar",
    "vehicle",
    "cycleway",
    "cycleway:left",
    "cycleway:right",
    "sidewalk",
    "psv",
    "bus",
]

ATRIBUTOS_LUGAR = [
    "name",
    "amenity",
    "shop",
    "leisure",
    "tourism",
    "office",
    "healthcare",
    "cuisine",
    "brand",
    "operator",
    "opening_hours",
    "addr:street",
    "addr:housenumber",
]

# Valores que se descartan cuando el POI no trae nombre. Son de dos clases:
# mobiliario urbano (escaños, basureros, estacionamientos) y equipamiento
# dentro de una parcela privada (piscinas, canchas y jardines de casas y
# condominios, que en Santiago se mapean desde imágenes satelitales y suman
# más de doce mil elementos). Con nombre propio entran igual, porque entonces
# corresponden a un recinto que alguien nombró.
SIN_NOMBRE_SE_DESCARTA = {
    "amenity": {
        "bench", "parking", "parking_space", "parking_entrance", "waste_basket",
        "waste_disposal", "bicycle_parking", "bicycle_repair_station", "toilets",
        "fountain", "recycling", "drinking_water", "shelter", "bbq", "grit_bin",
        "clock", "vending_machine", "telephone", "post_box", "smoking_area",
        "watering_place", "hunting_stand",
    },
    "leisure": {
        "swimming_pool", "pitch", "garden", "picnic_table", "bleachers",
        "outdoor_seating", "fitness_station", "track",
    },
}

TAGS_LUGARES = {
    "amenity": True,
    "shop": True,
    "leisure": True,
    "tourism": True,
    "office": True,
    "healthcare": True,
}


def _cpus() -> int:
    """Mitad de los nucleos disponibles, para no saturar la maquina."""
    return max(1, mp.cpu_count() // 2)


def _extraer(geometria, tags_filter) -> gpd.GeoDataFrame:
    config.DIR_CACHE_OSM.mkdir(parents=True, exist_ok=True)
    return qosm.convert_geometry_to_geodataframe(
        geometry_filter=geometria,
        tags_filter=tags_filter,
        working_directory=config.DIR_CACHE_OSM,
        verbosity_mode="transient",
        keep_all_tags=True,
        explode_tags=True,
        cpu_limit=_cpus(),
    )


def _seleccionar(gdf: gpd.GeoDataFrame, atributos: list[str]) -> gpd.GeoDataFrame:
    """Deja solo los atributos pedidos que existan, más la geometría."""
    columnas = [c for c in atributos if c in gdf.columns]
    salida = gdf[columnas + ["geometry"]].copy()
    salida.insert(0, "osm_id", gdf.index.astype(str))
    return salida.reset_index(drop=True)


def limite_area(area=None) -> gpd.GeoDataFrame:
    """Polígono del área de estudio, unión de sus comunas según OpenStreetMap.

    Las comunas chilenas están mapeadas como relaciones con
    `boundary=administrative` y `admin_level=8`. El bbox del área solo acota la
    búsqueda; el resultado es la unión de los polígonos, no el rectángulo. Si el
    área declara un `recorte`, los polígonos se cortan con él.

    Retorna un GeoDataFrame con una fila por comuna más su geometría, para que
    el área grande conserve de qué comuna viene cada parte.
    """
    area = area or config.area()
    limites = _extraer(box(*area.bbox), {"boundary": "administrative"})
    seleccion = limites[
        (limites["admin_level"] == config.NIVEL_ADMIN_COMUNA)
        & (limites["name"].isin(area.comunas))
        & (limites.geometry.geom_type.isin(["Polygon", "MultiPolygon"]))
    ]
    encontradas = set(seleccion["name"])
    faltantes = sorted(set(area.comunas) - encontradas)
    if faltantes:
        raise ValueError(
            f"No se encontraron en OpenStreetMap las comunas {faltantes} "
            f"con admin_level={config.NIVEL_ADMIN_COMUNA} dentro de {area.bbox}."
        )
    comunas = (
        seleccion[["name", "geometry"]]
        .rename(columns={"name": "comuna"})
        .dissolve(by="comuna")
        .reset_index()
    )
    comunas = gpd.GeoDataFrame(comunas, geometry="geometry", crs=limites.crs)

    if area.recorte is not None:
        comunas = comunas.clip(box(*area.recorte))
        comunas = comunas[~comunas.is_empty].reset_index(drop=True)
    return comunas


def vias(limite: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Todas las ways con tag `highway` dentro del límite.

    Se baja una sola vez el conjunto completo y después cada modo se deriva
    filtrando tags. Bajar una red por modo repetiria el trabajo y además
    produciría nodos distintos en cada red, lo que impide compararlas.
    """
    poligono = limite.geometry.union_all()
    crudo = _extraer(poligono, {"highway": True})
    lineas = crudo[crudo.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    # quackosm devuelve entera cualquier way que toque el polígono, así que
    # una avenida que solo roza el borde entraría completa y los largos de la
    # red dejarían de corresponder a la comuna. `clip` corta las geometrías en
    # el límite; el precio es que los tramos cortados quedan con un extremo
    # suelto, que es el comportamiento correcto para un estudio comunal.
    recortadas = lineas.clip(poligono)
    recortadas = recortadas[
        recortadas.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ]
    return _seleccionar(recortadas, ATRIBUTOS_VIA)


def lugares(limite: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Puntos de interés dentro del límite.

    Los POI de OSM vienen como nodos, ways cerradas o relaciones. Las
    geometrías no puntuales se reducen a su centroide para poder asignarlas a
    una calle.

    Un POI entra si tiene nombre propio o si, sin tenerlo, su categoría no está
    en `SIN_NOMBRE_SE_DESCARTA`. Exigir nombre dejaría fuera comercio real: en
    el Gran Santiago hay 2194 locales con tag `shop` y sin `name`, entre ellos
    70 botellerías, que existen en la calle aunque OSM no registre su razón
    social.
    """
    poligono = limite.geometry.union_all()
    crudo = _extraer(poligono, TAGS_LUGARES)
    seleccion = _seleccionar(crudo[_es_lugar(crudo)], ATRIBUTOS_LUGAR)
    metrico = seleccion.to_crs(config.CRS_METRICO)
    seleccion["geometry"] = metrico.geometry.centroid.to_crs(seleccion.crs)
    dentro = seleccion[seleccion.geometry.within(poligono)]
    return dentro.reset_index(drop=True)


def _es_lugar(crudo: gpd.GeoDataFrame) -> pd.Series:
    """Marca los POI que entran al grafo."""
    if "name" not in crudo.columns:
        return pd.Series(True, index=crudo.index)
    entra = crudo["name"].notna()
    descartar = pd.Series(False, index=crudo.index)
    for tag, valores in SIN_NOMBRE_SE_DESCARTA.items():
        if tag in crudo.columns:
            descartar |= crudo[tag].isin(valores)
    return entra | ~descartar


def descargar_dataset_curso(nombre: str, destino: Path | None = None) -> Path:
    """Baja y descomprime un `.tgz` publicado por el curso.

    Adaptado de `gdsutils.general.descargar_datos`: acá los errores se
    propagan en vez de imprimirse, para que el pipeline se detenga si una
    fuente falta.
    """
    destino = destino or config.DIR_DATOS
    destino.mkdir(parents=True, exist_ok=True)
    carpeta = destino / nombre
    if carpeta.exists():
        print(f"  {carpeta} ya existe, no se vuelve a descargar.")
        return carpeta

    url = f"{config.URL_DATOS_CURSO}/{nombre}.tgz"
    print(f"  Descargando {url}")
    try:
        temporal, _ = urllib.request.urlretrieve(url)
        with tarfile.open(temporal, "r:gz") as tar:
            tar.extractall(path=destino, filter="data")
    finally:
        urllib.request.urlcleanup()
    print(f"  Extraido en {carpeta}")
    return carpeta
