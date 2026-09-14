"""Rutas, selección del área de estudio y resolución de fuentes de datos.

Cada ruta se puede sobreescribir con una variable de entorno. Esto permite
mover los datos intermedios a una partición con espacio suficiente sin tocar
el código, que a escala de ciudad importa: el grafo del Gran Santiago ocupa
varios gigabytes entre parquet, JSON y GraphML.

    FROGQL_DATOS=/mnt/scratch/datos uv run python 01-preparar-datos.py

El área activa se elige con `--area` en la línea de comandos o con la variable
`FROGQL_AREA`. Los datos y las salidas de cada área viven en subdirectorios
separados, así que las dos escalas conviven sin pisarse.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from redosm.areas import AREAS, PREDETERMINADA, Area

RAIZ = Path(__file__).resolve().parent.parent

# Datos crudos e intermedios. No se versiona.
DIR_DATOS = Path(os.environ.get("FROGQL_DATOS", RAIZ / "datos"))
# Grafos exportados (GraphML, JSON, CSV) y figuras.
DIR_SALIDA = Path(os.environ.get("FROGQL_SALIDA", RAIZ / "salida"))
# Directorio de trabajo de quackosm: guarda el PBF y los parquet intermedios.
# Es común a las dos áreas, para no bajar dos veces el mismo extracto.
DIR_CACHE_OSM = Path(os.environ.get("FROGQL_CACHE_OSM", DIR_DATOS / "_quackosm"))

CRS_GEOGRAFICO = "EPSG:4326"
CRS_METRICO = "EPSG:32719"  # UTM 19S, metros

NIVEL_ADMIN_COMUNA = "8"

# Repositorio hermano con los datasets del curso de datos geográficos.
REPO_CURSO = Path(os.environ.get("GDS_CURSO", RAIZ.parent / "gds-course-materials"))
URL_DATOS_CURSO = "https://dcc.uchile.cl/~egraells/gds-data"

# Fuentes que se resuelven en orden: variable de entorno, repositorio del
# curso, descarga pública. `None` en la tercera posición significa que no hay
# versión publicada y la capa se omite si no está local.
FUENTES = {
    "sosafe": {
        "env": "FROGQL_SOSAFE",
        "curso": "sosafe/reportes-2024.parquet",
        "descarga": ("sosafe-clustering", "sosafe-clustering/reportes-quincena.parquet"),
    },
    "venues": {
        "env": "FROGQL_VENUES",
        "curso": "foursquare-santiago/venues.parquet",
        "descarga": ("foursquare-santiago", "foursquare-santiago/venues.parquet"),
    },
    "checkins": {
        "env": "FROGQL_CHECKINS",
        "curso": "foursquare-santiago/checkins.parquet",
        "descarga": ("foursquare-santiago", "foursquare-santiago/checkins.parquet"),
    },
    "zonas": {
        "env": "FROGQL_ZONAS",
        "curso": "censo2024-cartografia/Cartografia_censo2024_Pais_Zonal.parquet",
        "descarga": None,
    },
}

_ACTIVA: Area = AREAS[os.environ.get("FROGQL_AREA", PREDETERMINADA)]


def seleccionar(nombre: str | None = None) -> Area:
    """Fija el área de estudio activa y devuelve sus parámetros.

    Sin argumento, lee `--area` de la línea de comandos y, si no está, la
    variable `FROGQL_AREA`. Los scripts la llaman una vez al comienzo.
    """
    global _ACTIVA
    if nombre is None:
        nombre = _desde_linea_de_comandos() or os.environ.get(
            "FROGQL_AREA", PREDETERMINADA
        )
    if nombre not in AREAS:
        disponibles = ", ".join(sorted(AREAS))
        raise SystemExit(f"Área '{nombre}' desconocida. Disponibles: {disponibles}.")
    _ACTIVA = AREAS[nombre]
    return _ACTIVA


def _desde_linea_de_comandos() -> str | None:
    argumentos = sys.argv[1:]
    for i, argumento in enumerate(argumentos):
        if argumento == "--area" and i + 1 < len(argumentos):
            return argumentos[i + 1]
        if argumento.startswith("--area="):
            return argumento.split("=", 1)[1]
    return None


def area() -> Area:
    """Área de estudio activa."""
    return _ACTIVA


def dir_datos() -> Path:
    return DIR_DATOS / _ACTIVA.nombre


def dir_osm() -> Path:
    return dir_datos() / "osm"


def dir_contexto() -> Path:
    return dir_datos() / "contexto"


def dir_salida() -> Path:
    return DIR_SALIDA / _ACTIVA.nombre


def dir_grafos() -> Path:
    return dir_salida() / "graphml"


def dir_frogql() -> Path:
    return dir_salida() / "frogql"


def dir_figuras() -> Path:
    return dir_salida() / "figuras"


def crear_directorios() -> None:
    """Crea los directorios de trabajo y de salida del área activa."""
    for d in (
        DIR_DATOS,
        DIR_CACHE_OSM,
        dir_osm(),
        dir_contexto(),
        dir_grafos(),
        dir_frogql(),
        dir_figuras(),
    ):
        d.mkdir(parents=True, exist_ok=True)


def resolver(nombre: str, descargar: bool = True) -> Path | None:
    """Devuelve la ruta local de una fuente, descargándola si hace falta.

    Retorna `None` cuando la fuente no está disponible y no existe versión
    publicada. Quien llama decide si la capa es opcional.
    """
    spec = FUENTES[nombre]

    ruta_env = os.environ.get(spec["env"])
    if ruta_env:
        ruta = Path(ruta_env)
        if not ruta.exists():
            raise FileNotFoundError(f"{spec['env']}={ruta} no existe.")
        return ruta

    ruta_curso = REPO_CURSO / "data" / spec["curso"]
    if ruta_curso.exists():
        return ruta_curso

    if spec["descarga"] is None:
        return None

    dataset, relativa = spec["descarga"]
    ruta_local = DIR_DATOS / relativa
    if ruta_local.exists():
        return ruta_local
    if not descargar:
        return None

    from redosm.descarga import descargar_dataset_curso

    descargar_dataset_curso(dataset)
    return ruta_local if ruta_local.exists() else None
