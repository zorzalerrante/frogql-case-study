"""Construcción de la topología vial a partir de las ways de OpenStreetMap.

OSM pública las calles como ways: secuencias ordenadas de coordenadas con
tags. Una way puede atravesar varias esquinas sin que esas esquinas aparezcan
como elemento separado, y dos calles que se cruzan comparten la coordenada
pero no un identificador común. Convertir ese material en un grafo exige un
paso previo: agrupar coordenadas coincidentes en nodos y cortar cada way en
los nodos que comparte con otras.

Sin ese corte, una avenida que cruza diez esquinas queda como una sola arista
y la red resultante no tiene la conectividad real.

Adaptado de `gdsutils.redes.construir_grafo_desde_lineas` del curso de datos
geográficos. La diferencia está en que acá la partición geométrica y el armado
del grafo son dos funciones distintas: la primera corre una vez sobre todas
las ways y la segunda corre una vez por modo, sobre el mismo conjunto de
nodos.
"""

from __future__ import annotations

from collections import defaultdict

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point

from redosm import config


def _clusterizar(coords: np.ndarray, tolerancia: float) -> np.ndarray:
    """Agrupa coordenadas a distancia menor o igual a `tolerancia`.

    Usa un KDTree para encontrar los pares cercanos y union-find para
    fusionarlos. Es preferible a redondear a una grilla, porque dos puntos
    separados por centimetros pueden caer en celdas distintas si están cerca
    de un borde.
    """
    n = len(coords)
    padre = np.arange(n)

    def raiz(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    if tolerancia > 0 and n > 1:
        arbol = cKDTree(coords)
        for a, b in arbol.query_pairs(r=tolerancia, output_type="ndarray"):
            ra, rb = raiz(int(a)), raiz(int(b))
            if ra != rb:
                padre[ra] = rb

    raices = np.array([raiz(i) for i in range(n)])
    _, consecutivos = np.unique(raices, return_inverse=True)
    return consecutivos


def partir_en_intersecciones(
    vias: gpd.GeoDataFrame,
    tolerancia_metros: float = 1.5,
    crs_metrico: str = config.CRS_METRICO,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Corta las ways en sus intersecciones y devuelve nodos y segmentos.

    Parámetros
    ----------
    vias : GeoDataFrame de LineStrings con los tags de cada way.
    tolerancia_metros : distancia bajo la cual dos coordenadas se consideran
        el mismo nodo. Para OSM basta 1 a 2 metros; catalogos oficiales con
        ruido de digitalización necesitan más.
    crs_metrico : CRS proyectado en el que se miden distancias y largos.

    Retorna
    -------
    nodos : GeoDataFrame con `nodo_id` y geometría de punto.
    segmentos : GeoDataFrame con `u`, `v`, `largo_m`, los tags de la way de
        origen y la geometría del tramo.
    """
    if vias.empty:
        raise ValueError("El GeoDataFrame de vías está vacío.")

    crs_origen = vias.crs
    lineas = vias[vias.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    lineas = lineas.explode(index_parts=False).reset_index(drop=True)
    metrico = lineas.to_crs(crs_metrico)

    # Todas las coordenadas de todas las líneas, con el rango que ocupa cada
    # línea dentro del arreglo global.
    coordenadas: list[tuple[float, float]] = []
    rangos: list[tuple[int, int]] = []
    for geom in metrico.geometry:
        inicio = len(coordenadas)
        coordenadas.extend((c[0], c[1]) for c in geom.coords)
        rangos.append((inicio, len(coordenadas)))
    coordenadas = np.asarray(coordenadas, dtype=float)

    cluster_de_coord = _clusterizar(coordenadas, tolerancia_metros)
    clusters_por_linea = [list(cluster_de_coord[i:j]) for i, j in rangos]
    coords_por_linea = [[tuple(c) for c in coordenadas[i:j]] for i, j in rangos]

    # Un cluster es nodo del grafo si es extremo de alguna línea o si lo
    # comparten dos líneas distintas (una esquina).
    lineas_por_cluster: dict[int, set[int]] = defaultdict(set)
    for indice, clusters in enumerate(clusters_por_linea):
        for cid in clusters:
            lineas_por_cluster[int(cid)].add(indice)

    es_nodo: set[int] = set()
    for clusters in clusters_por_linea:
        es_nodo.add(int(clusters[0]))
        es_nodo.add(int(clusters[-1]))
    for cid, ids_linea in lineas_por_cluster.items():
        if len(ids_linea) >= 2:
            es_nodo.add(cid)

    numero = {cid: i for i, cid in enumerate(sorted(es_nodo))}

    coord_de_nodo: dict[int, tuple[float, float]] = {}
    for clusters, coords in zip(clusters_por_linea, coords_por_linea):
        for cid, coord in zip(clusters, coords):
            if int(cid) in numero:
                coord_de_nodo.setdefault(numero[int(cid)], coord)

    # Los segmentos se arman con los índices de nodo y la geometría, y los tags
    # de la way se pegan después con un join. Copiar los tags dentro del bucle
    # multiplicaría cada atributo por la cantidad de tramos en que se parte la
    # way, que a escala de ciudad son millones de celdas construidas en Python.
    atributos = [c for c in lineas.columns if c != "geometry"]
    us: list[int] = []
    vs: list[int] = []
    lineas_de_segmento: list[int] = []
    geometrias: list[LineString] = []
    for indice, (clusters, coords) in enumerate(zip(clusters_por_linea, coords_por_linea)):
        u = numero.get(int(clusters[0]))
        acumulado = [coords[0]]
        for cid, coord in zip(clusters[1:], coords[1:]):
            acumulado.append(coord)
            v = numero.get(int(cid))
            if v is None:
                continue
            if v != u and len(acumulado) >= 2:
                us.append(u)
                vs.append(v)
                lineas_de_segmento.append(indice)
                geometrias.append(LineString(acumulado))
            u = v
            acumulado = [coord]

    if not us:
        raise ValueError("La partición no generó segmentos.")

    segmentos = gpd.GeoDataFrame(
        {"u": us, "v": vs, "_linea": lineas_de_segmento},
        geometry=geometrias,
        crs=crs_metrico,
    )
    segmentos["largo_m"] = segmentos.length
    segmentos = segmentos.join(lineas[atributos], on="_linea").drop(columns="_linea")
    segmentos = segmentos.to_crs(crs_origen)
    segmentos.insert(0, "segmento_id", np.arange(len(segmentos)))

    ids = sorted(coord_de_nodo)
    nodos = gpd.GeoDataFrame(
        {"nodo_id": ids},
        geometry=[Point(coord_de_nodo[i]) for i in ids],
        crs=crs_metrico,
    ).to_crs(crs_origen)

    return nodos, segmentos


def grafo_desde_segmentos(
    nodos: gpd.GeoDataFrame,
    segmentos: gpd.GeoDataFrame,
    dirigido: bool = False,
    columna_sentido: str | None = None,
) -> nx.MultiGraph | nx.MultiDiGraph:
    """Arma el grafo de NetworkX con los segmentos entregados.

    Cuando `dirigido` es True y se entrega `columna_sentido`, cada segmento
    aporta un arco en el sentido de circulación: los de doble sentido aportan
    los dos. La columna debe contener `ambos`, `directo` o `inverso`, que es
    lo que devuelve `perfiles.sentido`.
    """
    grafo = nx.MultiDiGraph() if dirigido else nx.MultiGraph()

    coordenadas = {
        int(fila.nodo_id): (float(fila.geometry.x), float(fila.geometry.y))
        for fila in nodos.itertuples(index=False)
    }
    usados = set(segmentos["u"]).union(segmentos["v"])
    for nodo_id in sorted(usados):
        x, y = coordenadas[int(nodo_id)]
        grafo.add_node(int(nodo_id), x=x, y=y)

    atributos = [c for c in segmentos.columns if c not in ("u", "v")]
    # Se recorre con `to_dict` y no con `itertuples` porque varios tags de OSM
    # llevan dos puntos en el nombre (`cycleway:left`) y no son identificadores
    # válidos de Python.
    for fila in segmentos.to_dict("records"):
        datos = {c: fila[c] for c in atributos}
        u, v = int(fila["u"]), int(fila["v"])
        if not dirigido or columna_sentido is None:
            grafo.add_edge(u, v, **datos)
            continue
        modo = fila[columna_sentido]
        if modo in ("ambos", "directo"):
            grafo.add_edge(u, v, **datos)
        if modo in ("ambos", "inverso"):
            grafo.add_edge(v, u, **datos)

    return grafo


def componente_gigante(grafo: nx.Graph) -> nx.Graph:
    """Subgrafo de la componente conexa más grande.

    En redes dirigidas se usa la conectividad debil: un arco de sentido único
    no desconecta el barrio, solo obliga a rodear.
    """
    if grafo.is_directed():
        componentes = nx.weakly_connected_components(grafo)
    else:
        componentes = nx.connected_components(grafo)
    mayor = max(componentes, key=len)
    return grafo.subgraph(mayor).copy()


def resumen(grafo: nx.Graph) -> dict:
    """Descriptores basicos de una red vial.

    Las redes dirigidas representan una calle de doble sentido con dos arcos,
    así que contar arcos o sumar sus largos sobreestima la infraestructura.
    Por eso el largo y el grado se calculan sobre tramos distintos
    (`segmento_id`) y no sobre arcos, de modo que las tres redes sean
    comparables entre si.
    """
    n = grafo.number_of_nodes()
    arcos = grafo.number_of_edges()

    vistos: set = set()
    largo = 0.0
    tramos = 0
    for _, _, datos in grafo.edges(data=True):
        clave = datos.get("segmento_id")
        if clave is not None:
            if clave in vistos:
                continue
            vistos.add(clave)
        tramos += 1
        largo += float(datos.get("largo_m", 0.0))

    if grafo.is_directed():
        componentes = list(nx.weakly_connected_components(grafo))
    else:
        componentes = list(nx.connected_components(grafo))
    mayor = max((len(c) for c in componentes), default=0)

    return {
        "nodos": n,
        "tramos": tramos,
        "arcos": arcos,
        "km": largo / 1000.0,
        "grado_medio": (2 * tramos / n) if n else 0.0,
        "componentes": len(componentes),
        "cobertura_gcc": (mayor / n) if n else 0.0,
    }


def tabla_resumen(resumenes: dict[str, dict]) -> pd.DataFrame:
    """Ordena varios resumenes en una tabla legible."""
    return pd.DataFrame(resumenes).T[
        ["nodos", "tramos", "arcos", "km", "grado_medio", "componentes", "cobertura_gcc"]
    ]
