"""Capas no viales que se cuelgan de la red: reportes, zonas censales, venues.

Las tres capas comparten la misma forma: puntos o poligonos que se recortan a
la comuna y después se enganchan a la red vial por cercanía. La red de OSM es
el esqueleto; estas capas son lo que ocurre sobre ella.

Las reglas de limpieza de SOSAFE (categorías, grupos, anonimización del texto
libre) vienen de `gdsutils.sosafe` del curso de datos geográficos.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

from redosm import config

GRUPOS = {
    "Ambiental": "mantención urbana y medio ambiente",
    "Disturbios": "uso del espacio público y convivencia",
    "Delitos": "hechos delictuales",
}

COLORES_GRUPO = {
    "Ambiental": "#2a9d8f",
    "Disturbios": "#e9c46a",
    "Delitos": "#e76f51",
}

# Información de contacto en el texto libre de los reportes.
PATRON_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)
# Telefonos chilenos: movil 9 + 8 dígitos, fijo 2 + 8 dígitos, con prefijo de
# pais opcional. Exigir el bloque de 8 dígitos evita confundir patentes,
# fechas u horas con numeros de telefono.
PATRON_TELEFONO = re.compile(
    r"(?<!\w)\+?(?:56)?[\s.\-]?(?:9|2)?[\s.\-]?\d{4}[\s.\-]?\d{4}(?!\w)"
)

# Categorías de Foursquare que describen domicilios. Publicar su ubicación
# expone residencias particulares, así que quedan fuera del grafo.
CATEGORIAS_PRIVADAS = frozenset(
    {
        "Home (private)",
        "Residential Building (Apartment / Condo)",
        "Housing Development",
        "Assisted Living",
    }
)

COLUMNAS_CENSO = [
    "ID_ZONA",
    "COD_ZONA",
    "DISTRITO",
    "COMUNA",
    "n_per",
    "n_hog",
    "prom_edad",
    "prom_escolaridad18",
    "n_inmigrantes",
    "n_hog_unipersonales",
    "n_viv_hacinadas",
    "n_transporte_auto",
    "n_transporte_publico",
    "n_transporte_camina",
    "n_transporte_bicicleta",
]


def _normalizar(nombre: str) -> str:
    """Nombre de comuna en mayúsculas y sin tildes, para comparar fuentes.

    El Censo escribe las comunas en mayúsculas y OpenStreetMap en
    capitalización normal, y no siempre coinciden en los acentos.
    """
    sin_tildes = unicodedata.normalize("NFKD", str(nombre))
    sin_tildes = sin_tildes.encode("ascii", "ignore").decode("ascii")
    return sin_tildes.upper().strip()


def anonimizar(serie: pd.Series) -> pd.Series:
    """Reemplaza correos y telefonos del texto libre por marcas fijas.

    El filtro es conservador: prefiere borrar de más (un RUT de ocho dígitos
    también cae) antes que dejar pasar información de contacto.
    """
    texto = serie.fillna("")
    texto = texto.str.replace(PATRON_CORREO, "[correo]", regex=True)
    texto = texto.str.replace(PATRON_TELEFONO, "[telefono]", regex=True)
    return texto.where(serie.notna(), serie)


def cargar_reportes(limite: gpd.GeoDataFrame, ruta: Path | None = None) -> gpd.GeoDataFrame:
    """Reportes SOSAFE dentro del área, con el texto anonimizado.

    La fuente se resuelve en `config.resolver`: primero la variable de
    entorno `FROGQL_SOSAFE`, después el año completo del repositorio del
    curso y, si no está, la quincena publicada. El `reporte_id` es
    secuencial sobre los reportes ordenados por fecha, así que depende de la
    fuente que se haya usado.
    """
    ruta = ruta or config.resolver("sosafe")
    if ruta is None:
        raise FileNotFoundError("No hay fuente de reportes SOSAFE disponible.")

    reportes = gpd.read_parquet(ruta).to_crs(config.CRS_GEOGRAFICO)
    poligono = limite.to_crs(config.CRS_GEOGRAFICO).geometry.union_all()
    dentro = reportes[reportes.geometry.within(poligono)].copy()
    dentro = dentro.sort_values("created_at").reset_index(drop=True)

    dentro["reporte_id"] = [f"{i:06d}" for i in range(len(dentro))]
    if "description" in dentro.columns:
        dentro["description"] = anonimizar(dentro["description"])
    dentro["fecha"] = dentro["created_at"].dt.strftime("%Y-%m-%d")
    return dentro


def cargar_zonas(
    limite: gpd.GeoDataFrame,
    comunas: tuple[str, ...] | None = None,
    ruta: Path | None = None,
) -> gpd.GeoDataFrame | None:
    """Zonas censales del área con sus atributos de población.

    Devuelve `None` si la cartografía del Censo 2024 no está disponible. La
    capa es opcional: el grafo se arma igual sin ella.
    """
    ruta = ruta or config.resolver("zonas")
    if ruta is None:
        return None

    comunas = comunas or config.area().comunas
    buscadas = {_normalizar(c) for c in comunas}

    zonal = gpd.read_parquet(ruta)
    # La cartografía censal publica la geometría en una columna llamada
    # SHAPE. Se renombra para que el resto del paquete vea siempre
    # `geometry`.
    if zonal.geometry.name != "geometry":
        zonal = zonal.rename_geometry("geometry")
    zonas = zonal[zonal["COMUNA"].map(_normalizar).isin(buscadas)].copy()
    if zonas.empty:
        return None

    columnas = [c for c in COLUMNAS_CENSO if c in zonas.columns]
    zonas = zonas[columnas + ["geometry"]].to_crs(config.CRS_GEOGRAFICO)

    # El filtro por comuna no basta cuando el área está recortada: la parte
    # rural de Pudahuel o de San Bernardo queda fuera del polígono pero sus
    # zonas censales siguen teniendo el nombre de la comuna. Se conservan las
    # zonas cuyo punto representativo cae dentro del área, de modo que los
    # atributos censales sigan describiendo la zona completa.
    poligono = limite.to_crs(config.CRS_GEOGRAFICO).geometry.union_all()
    dentro = zonas.geometry.representative_point().within(poligono)
    zonas = zonas[dentro]
    if zonas.empty:
        return None

    zonas["zona_id"] = zonas["ID_ZONA"].astype("int64").astype(str)
    return zonas.reset_index(drop=True)


def cargar_venues(limite: gpd.GeoDataFrame) -> gpd.GeoDataFrame | None:
    """Venues de Foursquare dentro del área, con su número de check-ins.

    El dataset es el subconjunto de Santiago del check-in global publicado
    por Yang et al. (2019). Los venues no traen nombre, solo categoría, y las
    categorías residenciales quedan excluidas.
    """
    ruta_venues = config.resolver("venues")
    if ruta_venues is None:
        return None

    venues = pd.read_parquet(ruta_venues)
    puntos = gpd.GeoDataFrame(
        venues,
        geometry=gpd.points_from_xy(venues["lon"], venues["lat"]),
        crs=config.CRS_GEOGRAFICO,
    )
    poligono = limite.to_crs(config.CRS_GEOGRAFICO).geometry.union_all()
    dentro = puntos[puntos.geometry.within(poligono)].copy()
    dentro = dentro[~dentro["category"].isin(CATEGORIAS_PRIVADAS)]

    ruta_checkins = config.resolver("checkins")
    if ruta_checkins is not None:
        checkins = pd.read_parquet(ruta_checkins, columns=["venue_id"])
        conteo = checkins["venue_id"].value_counts()
        dentro["checkins"] = dentro["venue_id"].map(conteo).fillna(0).astype(int)
    else:
        dentro["checkins"] = 0

    return dentro.reset_index(drop=True)
