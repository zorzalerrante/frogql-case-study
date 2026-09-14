"""Armado del grafo de propiedades que consume froGQL.

Un grafo de propiedades tiene nodos y aristas etiquetados, ambos con
atributos. Acá conviven seis tipos de nodo y siete tipos de arista:

    (:Interseccion) -[:CONECTA_AUTO|CONECTA_BICI|CONECTA_PEATON]-> (:Interseccion)
    (:Interseccion) -[:EN_CALLE]-> (:Calle)
    (:Lugar)        -[:EN_CALLE]-> (:Calle)
    (:Reclamo)      -[:EN_CALLE]-> (:Calle)
    (:Venue)        -[:EN_CALLE]-> (:Calle)
    (:Calle)        ~[:CRUZA_CON]~ (:Calle)
    (:Reclamo)      -[:CERCA_DE]-> (:Lugar)
    (:Lugar|:Reclamo|:Venue) -[:EN_ZONA]-> (:ZonaCensal)

La calle con nombre se reifica como nodo. El tramo entre dos esquinas es una
arista, pero el eje con nombre necesita ser nodo para que cualquier par de
entidades pueda colgarse de él. Con la calle como nodo, "los lugares que están
en la misma calle que un reclamo" es un patrón de dos aristas.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from redosm import calles as mod_calles
from redosm import config
from redosm.perfiles import PERFILES

# Atributos del segmento que viajan a la arista de circulación.
ATRIBUTOS_TRAMO = {
    "highway": "tipo",
    "name": "calle",
    "surface": "superficie",
    "maxspeed": "velocidad_max",
    "lanes": "pistas",
    "lit": "iluminacion",
}

ATRIBUTOS_LUGAR = {
    "name": "nombre",
    "amenity": "amenity",
    "shop": "shop",
    "leisure": "leisure",
    "tourism": "tourism",
    "office": "office",
    "healthcare": "healthcare",
    "cuisine": "cocina",
    "brand": "marca",
    "operator": "operador",
    "opening_hours": "horario",
    "addr:street": "direccion_calle",
    "addr:housenumber": "direccion_numero",
}

ATRIBUTOS_RECLAMO = {
    "reporte_id": "reporte_id",
    "categoria": "categoria",
    "grupo": "grupo",
    "fecha": "fecha",
    "hora": "hora",
    "dia_semana": "dia_semana",
    "description": "descripcion",
    "likes": "likes",
    "comments": "comentarios",
}

ATRIBUTOS_VENUE = {"venue_id": "venue_id", "category": "categoria", "checkins": "checkins"}


def _valor(v):
    """Convierte un valor de pandas a un tipo que JSON acepta, o `None`."""
    if v is None:
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        v = float(v)
    if isinstance(v, float) and (pd.isna(v) or np.isinf(v)):
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if v is pd.NaT:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


def _texto(valor) -> str | None:
    """Valor de texto no vacío, o `None`. Evita que un NaN llegue al JSON."""
    limpio = _valor(valor)
    if limpio is None or limpio == "":
        return None
    return str(limpio)


def _props(fila, mapa: dict[str, str]) -> dict:
    """Extrae atributos de una fila según un mapa `origen -> destino`."""
    salida = {}
    for origen, destino in mapa.items():
        if origen not in fila:
            continue
        valor = _valor(fila[origen])
        if valor is not None and valor != "":
            salida[destino] = valor
    return salida


@dataclass
class GrafoPropiedades:
    """Nodos y aristas listos para serializar."""

    nodos: list[dict] = field(default_factory=list)
    aristas: list[dict] = field(default_factory=list)

    def agregar_nodo(self, identificador: str, etiqueta: str, props: dict) -> None:
        self.nodos.append({"id": identificador, "labels": [etiqueta], "props": props})

    def agregar_arista(
        self, origen: str, destino: str, etiqueta: str, props: dict, dirigida: bool = True
    ) -> None:
        self.aristas.append(
            {
                "id": f"a{len(self.aristas)}",
                "labels": [etiqueta],
                "endpoints": [origen, destino],
                "directionality": "->" if dirigida else "~~",
                "props": props,
            }
        )

    def conteo_nodos(self) -> pd.Series:
        return pd.Series([n["labels"][0] for n in self.nodos]).value_counts().rename("nodos")

    def conteo_aristas(self) -> pd.Series:
        return pd.Series([a["labels"][0] for a in self.aristas]).value_counts().rename("aristas")


def _asignar_zona(puntos: gpd.GeoDataFrame, zonas: gpd.GeoDataFrame | None) -> list:
    """Identificador de la zona censal que contiene a cada punto."""
    if zonas is None or puntos.empty:
        return [None] * len(puntos)
    union = gpd.sjoin(
        puntos[["geometry"]].to_crs(config.CRS_GEOGRAFICO),
        zonas[["zona_id", "geometry"]].to_crs(config.CRS_GEOGRAFICO),
        how="left",
        predicate="within",
    )
    union = union[~union.index.duplicated(keep="first")]
    return union["zona_id"].reindex(puntos.index).tolist()


def _agregar_capa_de_puntos(
    grafo: GrafoPropiedades,
    puntos: gpd.GeoDataFrame,
    etiqueta: str,
    prefijo: str,
    columna_id: str,
    atributos: dict[str, str],
    asignacion: pd.DataFrame,
    zonas_de_punto: list,
    props_extra=None,
) -> list[str]:
    """Agrega una capa de puntos con sus aristas EN_CALLE y EN_ZONA.

    Retorna los identificadores de los nodos creados, en el orden de `puntos`,
    para que quien llame pueda seguir colgándoles aristas.
    """
    registros = puntos.drop(columns="geometry").to_dict("records")
    xs = shapely.get_x(puntos.geometry.values)
    ys = shapely.get_y(puntos.geometry.values)
    calle_ids = asignacion["calle_id"].tolist()
    distancias = asignacion["distancia_m"].tolist()
    origenes = asignacion["origen"].tolist()

    identificadores = []
    for i, fila in enumerate(registros):
        identificador = f"{prefijo}:{fila[columna_id]}"
        identificadores.append(identificador)
        props = _props(fila, atributos)
        props["lon"] = round(float(xs[i]), 6)
        props["lat"] = round(float(ys[i]), 6)
        if props_extra is not None:
            props.update(props_extra(fila))
        grafo.agregar_nodo(identificador, etiqueta, props)

        calle_id = calle_ids[i]
        if isinstance(calle_id, str):
            props_calle = {"origen": str(origenes[i])}
            distancia = distancias[i]
            if distancia is not None and not pd.isna(distancia):
                props_calle["distancia_m"] = round(float(distancia), 1)
            grafo.agregar_arista(identificador, f"calle:{calle_id}", "EN_CALLE", props_calle)

        zona = zonas_de_punto[i]
        if isinstance(zona, str):
            grafo.agregar_arista(identificador, f"zona:{zona}", "EN_ZONA", {})
    return identificadores


def construir(
    nodos_red: gpd.GeoDataFrame,
    segmentos: gpd.GeoDataFrame,
    calles: gpd.GeoDataFrame,
    lugares: gpd.GeoDataFrame,
    reclamos: gpd.GeoDataFrame,
    zonas: gpd.GeoDataFrame | None = None,
    venues: gpd.GeoDataFrame | None = None,
    distancia_calle_m: float = 40.0,
    distancia_cercania_m: float = 50.0,
    verboso: bool = True,
) -> GrafoPropiedades:
    """Arma el grafo de propiedades con todas las capas del área de estudio."""
    grafo = GrafoPropiedades()

    def avisar(texto: str) -> None:
        if verboso:
            print(f"  {texto}")

    # --- Calles -------------------------------------------------------
    for fila in calles.drop(columns="geometry").to_dict("records"):
        props = {
            "calle_id": fila["calle_id"],
            "nombre": _texto(fila["nombre"]),
            "largo_m": round(float(fila["largo_m"]), 1),
            "segmentos": int(fila["segmentos"]),
        }
        for extra in ("tipo", "comuna"):
            valor = _texto(fila.get(extra))
            if valor is not None:
                props[extra] = valor
        for modo in PERFILES:
            columna = f"permite_{modo}"
            if columna in fila:
                props[columna] = bool(fila[columna])
        grafo.agregar_nodo(f"calle:{fila['calle_id']}", "Calle", props)
    avisar(f"Calles: {len(calles)}")

    # --- Intersecciones ----------------------------------------------
    grado = pd.concat([segmentos["u"], segmentos["v"]]).value_counts()
    ids_nodo = nodos_red["nodo_id"].to_numpy()
    xs = shapely.get_x(nodos_red.geometry.values)
    ys = shapely.get_y(nodos_red.geometry.values)
    grados = grado.reindex(ids_nodo).fillna(0).astype(int).to_numpy()
    for i, nodo_id in enumerate(ids_nodo):
        grafo.agregar_nodo(
            f"nodo:{int(nodo_id)}",
            "Interseccion",
            {
                "lon": round(float(xs[i]), 6),
                "lat": round(float(ys[i]), 6),
                "grado": int(grados[i]),
            },
        )
    avisar(f"Intersecciones: {len(nodos_red)}")

    # --- Tramos de circulación, uno por modo --------------------------
    for modo, perfil in PERFILES.items():
        permitidos = segmentos[segmentos[f"permite_{modo}"]]
        antes = len(grafo.aristas)
        for fila in permitidos.drop(columns="geometry").to_dict("records"):
            props = _props(fila, ATRIBUTOS_TRAMO)
            props["largo_m"] = round(float(fila["largo_m"]), 1)
            props["modo"] = modo
            calle_id = _texto(fila.get("calle_id"))
            if calle_id is not None:
                props["calle_id"] = calle_id
            if modo == "bici" and "ciclovia" in fila:
                props["ciclovia"] = bool(fila["ciclovia"])
            u, v = f"nodo:{int(fila['u'])}", f"nodo:{int(fila['v'])}"
            if not perfil.dirigido:
                grafo.agregar_arista(u, v, perfil.etiqueta, props, dirigida=False)
                continue
            if fila["sentido"] in ("ambos", "directo"):
                grafo.agregar_arista(u, v, perfil.etiqueta, props)
            if fila["sentido"] in ("ambos", "inverso"):
                grafo.agregar_arista(v, u, perfil.etiqueta, props)
        avisar(f"{perfil.etiqueta}: {len(grafo.aristas) - antes}")

    # --- Intersección en calle ---------------------------------------
    relacion = mod_calles.calles_por_nodo(segmentos)
    for nodo_id, calle_id in zip(relacion["nodo_id"].tolist(), relacion["calle_id"].tolist()):
        grafo.agregar_arista(f"nodo:{int(nodo_id)}", f"calle:{calle_id}", "EN_CALLE", {})
    avisar(f"EN_CALLE desde intersecciones: {len(relacion)}")

    # --- Cruces entre calles -----------------------------------------
    esquinas = mod_calles.cruces(segmentos)
    for a, b, cuantas in zip(
        esquinas["calle_a"].tolist(), esquinas["calle_b"].tolist(), esquinas["esquinas"].tolist()
    ):
        grafo.agregar_arista(
            f"calle:{a}", f"calle:{b}", "CRUZA_CON", {"esquinas": int(cuantas)}, dirigida=False
        )
    avisar(f"CRUZA_CON: {len(esquinas)}")

    # --- Zonas censales ----------------------------------------------
    if zonas is not None:
        columnas = [c for c in zonas.columns if c not in ("geometry", "zona_id")]
        for fila in zonas.drop(columns="geometry").to_dict("records"):
            props = {"zona_id": fila["zona_id"]}
            props.update({c.lower(): _valor(fila[c]) for c in columnas})
            grafo.agregar_nodo(
                f"zona:{fila['zona_id']}",
                "ZonaCensal",
                {k: v for k, v in props.items() if v is not None},
            )
        avisar(f"ZonaCensal: {len(zonas)}")

    # --- Lugares ------------------------------------------------------
    ids_lugar = _agregar_capa_de_puntos(
        grafo,
        lugares,
        "Lugar",
        "lugar",
        "osm_id",
        ATRIBUTOS_LUGAR,
        mod_calles.asignar_calle(
            lugares, segmentos, calles, distancia_calle_m, columna_declarada="addr:street"
        ),
        _asignar_zona(lugares, zonas),
        props_extra=lambda fila: {
            "osm_id": fila["osm_id"],
            "categoria": _categoria_lugar(fila),
            "etiqueta": _etiqueta_lugar(fila),
        },
    )
    avisar(f"Lugar: {len(ids_lugar)}")

    # --- Reclamos -----------------------------------------------------
    ids_reclamo = _agregar_capa_de_puntos(
        grafo,
        reclamos,
        "Reclamo",
        "reclamo",
        "reporte_id",
        ATRIBUTOS_RECLAMO,
        mod_calles.asignar_calle(reclamos, segmentos, calles, distancia_calle_m),
        _asignar_zona(reclamos, zonas),
    )
    avisar(f"Reclamo: {len(ids_reclamo)}")

    # --- Venues -------------------------------------------------------
    if venues is not None and not venues.empty:
        ids_venue = _agregar_capa_de_puntos(
            grafo,
            venues,
            "Venue",
            "venue",
            "venue_id",
            ATRIBUTOS_VENUE,
            mod_calles.asignar_calle(venues, segmentos, calles, distancia_calle_m),
            _asignar_zona(venues, zonas),
        )
        avisar(f"Venue: {len(ids_venue)}")

    # --- Proximidad entre reclamos y lugares --------------------------
    antes = len(grafo.aristas)
    for i, j, distancia in _pares_cercanos(reclamos, lugares, distancia_cercania_m):
        grafo.agregar_arista(
            ids_reclamo[i], ids_lugar[j], "CERCA_DE", {"distancia_m": round(distancia, 1)}
        )
    avisar(f"CERCA_DE: {len(grafo.aristas) - antes}")

    return grafo


def _etiqueta_lugar(fila: dict) -> str:
    """Cómo mostrar el lugar en un resultado.

    Buena parte de los POI de OSM no trae `name` y aun así corresponde a un
    local real. Para esos la etiqueta es la categoría entre paréntesis, de modo
    que una consulta que lista lugares siga siendo legible y quede a la vista
    que el nombre falta en el mapa, no en el dato.
    """
    nombre = _texto(fila.get("name"))
    if nombre is not None:
        return nombre
    return f"({_categoria_lugar(fila)})"


def _categoria_lugar(fila: dict) -> str:
    """Categoría principal de un POI: el primer tag temático con valor."""
    for llave in ("amenity", "shop", "leisure", "tourism", "healthcare", "office"):
        valor = _texto(fila.get(llave))
        if valor:
            return f"{llave}={valor}"
    return "sin_categoria"


def _pares_cercanos(
    origen: gpd.GeoDataFrame, destino: gpd.GeoDataFrame, radio_m: float
) -> Iterator[tuple[int, int, float]]:
    """Pares de puntos a menos de `radio_m`, por posición en cada tabla.

    Usa un árbol KD sobre las coordenadas proyectadas. Bufferizar cada punto y
    cruzarlo con un join espacial da el mismo resultado, pero construye un
    polígono por punto: con medio millón de reportes eso no cabe en memoria.
    """
    if origen.empty or destino.empty:
        return
    coords_origen = shapely.get_coordinates(origen.geometry.to_crs(config.CRS_METRICO).values)
    coords_destino = shapely.get_coordinates(destino.geometry.to_crs(config.CRS_METRICO).values)
    arbol = cKDTree(coords_destino)
    for i, vecinos in enumerate(arbol.query_ball_point(coords_origen, r=radio_m)):
        if not vecinos:
            continue
        indices = np.asarray(vecinos)
        distancias = np.linalg.norm(coords_destino[indices] - coords_origen[i], axis=1)
        for j, distancia in zip(indices.tolist(), distancias.tolist()):
            yield i, j, distancia
