"""Serialización de los grafos a GraphML y a los formatos de entrada de froGQL.

Tres salidas, tres consumidores distintos:

- **GraphML**: formato XML estándar que leen NetworkX, igraph, Gephi y
  Cytoscape. Se escribe una por modo de transporte más una con el grafo
  completo.
- **JSON de froGQL**: `{"nodes": [...], "edges": [...]}`. Es la vía de entrada
  que conserva la direccionalidad por arista, incluidas las no dirigidas.
- **CSV de froGQL**: un archivo por etiqueta más `spanner_import_config.json`.
  El cargador CSV trata toda arista como dirigida, así que las relaciones no
  dirigidas se escriben en los dos sentidos.

Las tres se escriben recorriendo los datos en vez de materializar el documento
completo en memoria. A escala de comuna da igual; a escala de ciudad el JSON
pasa del gigabyte y la diferencia es entre correr y no correr.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import pandas as pd
from shapely.geometry.base import BaseGeometry

# Tipo declarado en la cabecera de GraphML para cada tipo de Python.
TIPOS_GRAPHML = {bool: "boolean", int: "long", float: "double", str: "string"}
TIPOS_CSV = {bool: "BOOL", int: "INT64", float: "FLOAT64", str: "STRING"}

# Separadores del JSON, sin espacios. `03-consultas.py` cuenta las aristas no
# dirigidas buscando la marca literal, así que el formato tiene que ser fijo.
SEPARADORES = (",", ":")


def _plano(valor):
    """Reduce un valor a algo que GraphML acepte, o a `None` si falta.

    La comprobación de ausencia va antes que la de tipo: un tag que OSM no trae
    llega como `float("nan")`, que es instancia de `float` y pasaría el filtro
    de tipos primitivos. Terminaría escrito en el XML como el texto "nan".
    """
    if isinstance(valor, BaseGeometry):
        return valor.wkt
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(valor, (bool, int, float, str)):
        return valor
    return str(valor)


def _tipo(valor) -> type:
    return bool if isinstance(valor, bool) else type(valor)


def _unificar(tipos: set[type]) -> type:
    """Tipo común de una clave. Si hay mezcla que no sea int con float, texto."""
    if len(tipos) == 1:
        return next(iter(tipos))
    if tipos <= {int, float}:
        return float
    return str


def _declaraciones(registros: Iterable[dict]) -> dict[str, type]:
    """Tipo de cada clave presente en una colección de atributos."""
    vistos: dict[str, set[type]] = {}
    for atributos in registros:
        for clave, valor in atributos.items():
            limpio = _plano(valor)
            if limpio is None:
                continue
            vistos.setdefault(clave, set()).add(_tipo(limpio))
    return {clave: _unificar(tipos) for clave, tipos in vistos.items()}


def _texto(valor, tipo: type) -> str:
    if tipo is bool:
        return "true" if valor else "false"
    if tipo is str:
        return escape(str(valor))
    return escape(str(valor))


def escribir_graphml(
    ruta: Path,
    nodos: Callable[[], Iterator[tuple]],
    aristas: Callable[[], Iterator[tuple]],
    dirigido: bool = True,
) -> Path:
    """Escribe un GraphML recorriendo los datos dos veces.

    `nodos` y `aristas` son funciones que devuelven un iterador nuevo en cada
    llamada. La primera pasada declara el tipo de cada atributo, que GraphML
    exige en la cabecera, y la segunda escribe los elementos.

    Cada elemento de `nodos` es `(id, atributos)`. Cada elemento de `aristas`
    es `(origen, destino, atributos)` y, opcionalmente, un cuarto valor que
    dice si esa arista es dirigida.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)

    claves_nodo = _declaraciones(atributos for _, atributos in nodos())
    claves_arista = _declaraciones(fila[2] for fila in aristas())

    with open(ruta, "w", encoding="utf-8") as salida:
        salida.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        salida.write(
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns '
            'http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">\n'
        )
        for ambito, claves in (("node", claves_nodo), ("edge", claves_arista)):
            salida.writelines(f'  <key id={quoteattr(clave)} for="{ambito}" '
                    f"attr.name={quoteattr(clave)} "
                    f'attr.type="{TIPOS_GRAPHML[tipo]}"/>\n' for clave, tipo in claves.items())
        borde = "directed" if dirigido else "undirected"
        salida.write(f'  <graph id="G" edgedefault="{borde}">\n')

        for identificador, atributos in nodos():
            salida.write(f"    <node id={quoteattr(str(identificador))}>\n")
            for clave, valor in atributos.items():
                limpio = _plano(valor)
                if limpio is None or clave not in claves_nodo:
                    continue
                tipo = claves_nodo[clave]
                salida.write(
                    f"      <data key={quoteattr(clave)}>"
                    f"{_texto(limpio, tipo)}</data>\n"
                )
            salida.write("    </node>\n")

        for numero, fila in enumerate(aristas()):
            origen, destino, atributos = fila[0], fila[1], fila[2]
            propia = fila[3] if len(fila) > 3 else None
            marca = ""
            if propia is not None and propia != dirigido:
                marca = f' directed="{"true" if propia else "false"}"'
            salida.write(
                f'    <edge id="e{numero}" source={quoteattr(str(origen))} '
                f"target={quoteattr(str(destino))}{marca}>\n"
            )
            for clave, valor in atributos.items():
                limpio = _plano(valor)
                if limpio is None or clave not in claves_arista:
                    continue
                tipo = claves_arista[clave]
                salida.write(
                    f"      <data key={quoteattr(clave)}>"
                    f"{_texto(limpio, tipo)}</data>\n"
                )
            salida.write("    </edge>\n")

        salida.write("  </graph>\n</graphml>\n")
    return ruta


def exportar_red(grafo, ruta: Path) -> Path:
    """Escribe a GraphML una red de NetworkX sin copiarla a otra estructura."""
    return escribir_graphml(
        ruta,
        nodos=lambda: ((n, d) for n, d in grafo.nodes(data=True)),
        aristas=lambda: ((u, v, d) for u, v, d in grafo.edges(data=True)),
        dirigido=grafo.is_directed(),
    )


def exportar_grafo_propiedades(grafo_propiedades, ruta: Path) -> Path:
    """Escribe a GraphML el grafo de propiedades completo.

    La etiqueta de cada nodo y de cada arista viaja en el atributo `label`, que
    es como GraphML representa los grafos con varios tipos de entidad.
    """
    return escribir_graphml(
        ruta,
        nodos=lambda: (
            (n["id"], {"label": n["labels"][0], **n["props"]})
            for n in grafo_propiedades.nodos
        ),
        aristas=lambda: (
            (
                a["endpoints"][0],
                a["endpoints"][1],
                {"label": a["labels"][0], **a["props"]},
                a["directionality"] == "->",
            )
            for a in grafo_propiedades.aristas
        ),
        dirigido=True,
    )


def exportar_frogql_json(grafo_propiedades, ruta: Path) -> Path:
    """Escribe el JSON que lee `frogql.import_json`.

    Los elementos se serializan de a uno. `allow_nan=False` corta el paso a los
    NaN de pandas: JSON no los admite y el cargador de froGQL falla con un
    error de parseo difícil de rastrear hasta la columna que los produjo. Los
    separadores van sin espacios: a escala de ciudad son millones de elementos
    y el espacio decorativo cuesta decenas de megabytes.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as salida:
        salida.write('{"nodes":[')
        for i, nodo in enumerate(grafo_propiedades.nodos):
            if i:
                salida.write(",")
            salida.write(json.dumps(nodo, ensure_ascii=False, allow_nan=False, separators=SEPARADORES))
        salida.write('],"edges":[')
        for i, arista in enumerate(grafo_propiedades.aristas):
            if i:
                salida.write(",")
            salida.write(json.dumps(arista, ensure_ascii=False, allow_nan=False, separators=SEPARADORES))
        salida.write("]}")
    return ruta


def _limpiar_texto(valor):
    """Colapsa los espacios en blanco del texto que va a un CSV.

    El cargador CSV de froGQL corta los registros por salto de línea, sin
    reconocer los que van dentro de un campo entrecomillado. Una descripción de
    varias líneas se convertiría en varios nodos. El JSON no tiene esta
    restricción y conserva el texto original.
    """
    if isinstance(valor, str):
        return " ".join(valor.split())
    return valor


def _columnas_y_tipos(registros: Iterable[dict], previas: list[str]) -> dict[str, type]:
    """Columnas de un CSV en orden de aparición, con el tipo de cada una."""
    tipos: dict[str, set[type]] = {clave: set() for clave in previas}
    for atributos in registros:
        for clave, valor in atributos.items():
            if valor is None:
                continue
            tipos.setdefault(clave, set()).add(_tipo(valor))
    return {clave: _unificar(t) if t else str for clave, t in tipos.items()}


def exportar_frogql_csv(grafo_propiedades, directorio: Path) -> Path:
    """Escribe el paquete CSV que lee `frogql.import_csv`.

    El cargador deduce la etiqueta de cada nodo del nombre del archivo, así que
    `Calle.csv` produce nodos `:Calle`. Para las aristas, la etiqueta sale del
    campo `label` del config y los extremos de las columnas `SRC_ID` y
    `DST_ID`.
    """
    directorio.mkdir(parents=True, exist_ok=True)
    archivos = []

    etiquetas_nodo = sorted({n["labels"][0] for n in grafo_propiedades.nodos})
    for etiqueta in etiquetas_nodo:
        seleccion = (n for n in grafo_propiedades.nodos if n["labels"][0] == etiqueta)
        columnas = _columnas_y_tipos(
            (n["props"] for n in grafo_propiedades.nodos if n["labels"][0] == etiqueta),
            ["vid"],
        )
        nombre = f"{etiqueta}.csv"
        with open(directorio / nombre, "w", encoding="utf-8", newline="") as salida:
            escritor = csv.DictWriter(salida, fieldnames=list(columnas), extrasaction="ignore")
            escritor.writeheader()
            for nodo in seleccion:
                fila = {"vid": nodo["id"]}
                fila.update({k: _limpiar_texto(v) for k, v in nodo["props"].items()})
                escritor.writerow(fila)
        archivos.append(
            {"path": nombre, "columns": {c: TIPOS_CSV[t] for c, t in columnas.items()}}
        )

    etiquetas_arista = sorted({a["labels"][0] for a in grafo_propiedades.aristas})
    for etiqueta in etiquetas_arista:
        columnas = _columnas_y_tipos(
            (a["props"] for a in grafo_propiedades.aristas if a["labels"][0] == etiqueta),
            ["SRC_ID", "DST_ID"],
        )
        nombre = f"{etiqueta.lower()}.csv"
        with open(directorio / nombre, "w", encoding="utf-8", newline="") as salida:
            escritor = csv.DictWriter(salida, fieldnames=list(columnas), extrasaction="ignore")
            escritor.writeheader()
            for arista in grafo_propiedades.aristas:
                if arista["labels"][0] != etiqueta:
                    continue
                origen, destino = arista["endpoints"]
                props = {k: _limpiar_texto(v) for k, v in arista["props"].items()}
                escritor.writerow({"SRC_ID": origen, "DST_ID": destino, **props})
                if arista["directionality"] == "~~":
                    escritor.writerow({"SRC_ID": destino, "DST_ID": origen, **props})
        archivos.append(
            {
                "path": nombre,
                "label": etiqueta,
                "columns": {c: TIPOS_CSV[t] for c, t in columnas.items()},
            }
        )

    with open(directorio / "spanner_import_config.json", "w", encoding="utf-8") as salida:
        json.dump({"files": archivos}, salida, ensure_ascii=False, indent=2)
    return directorio
