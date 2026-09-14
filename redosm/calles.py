"""Agregación de segmentos en calles con nombre y asignación de puntos.

El grafo vial tiene como nodos las intersecciones y como aristas los tramos
entre ellas. Una calle es otra cosa: el conjunto de tramos que comparten
nombre. La distinción importa para las consultas del caso de estudio, porque
un reclamo no ocurre en un tramo particular sino en una dirección, y quien
pregunta por "los lugares de la misma calle" piensa en el eje completo.

La identidad de una calle combina dos criterios. El primero es el tag `name` de
OSM. El segundo es la conectividad: los tramos que comparten nombre y además
están unidos entre sí forman un eje, y los que comparten nombre sin tocarse
forman ejes distintos.

El segundo criterio es necesario a escala de ciudad. En el Gran Santiago hay
25 873 nombres de calle distintos y 4672 de ellos tienen tramos separados por
más de cinco kilómetros: Los Aromos son 28 ways repartidas por varias comunas.
Agruparlas por nombre las volvería un solo nodo `Calle` y la consulta
"lugares en la misma calle que este reclamo" devolvería locales de la otra
punta de la ciudad. Partir por componente conexa las separa y, al mismo tiempo,
mantiene entera una avenida que sí cruza varias comunas.

Un tercer paso deshace los cortes accidentales: cuando a un tramo intermedio le
falta el tag `name`, la componente se parte en dos y los dos pedazos quedan a
pocos metros. `_unir_ejes_cercanos` los vuelve a juntar.
"""

from __future__ import annotations

import re
import unicodedata

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from redosm import config


def identificador(nombre: str) -> str:
    """Convierte un nombre de calle en un identificador ASCII estable."""
    sin_acentos = unicodedata.normalize("NFKD", str(nombre))
    sin_acentos = sin_acentos.encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")
    return limpio or "sin-nombre"


def _ejes_conexos(u: np.ndarray, v: np.ndarray, codigos_nombre: np.ndarray) -> np.ndarray:
    """Eje al que pertenece cada segmento con nombre.

    Dos segmentos están en el mismo eje si comparten nombre y existe un camino
    entre ellos usando solo segmentos de ese nombre. El cálculo trata cada par
    (intersección, nombre) como un vértice y cada segmento como una arista, y
    pide las componentes conexas de ese grafo auxiliar.
    """
    cantidad_nombres = int(codigos_nombre.max()) + 1
    clave_u = u * cantidad_nombres + codigos_nombre
    clave_v = v * cantidad_nombres + codigos_nombre
    _, inverso = np.unique(np.concatenate([clave_u, clave_v]), return_inverse=True)

    total = len(u)
    indice_u, indice_v = inverso[:total], inverso[total:]
    vertices = int(inverso.max()) + 1
    matriz = coo_matrix(
        (np.ones(total, dtype=np.int8), (indice_u, indice_v)),
        shape=(vertices, vertices),
    )
    _, etiquetas = connected_components(matriz, directed=False)
    return etiquetas[indice_u]


def _unir_ejes_cercanos(
    ejes: np.ndarray,
    geometrias: gpd.GeoSeries,
    nombres: pd.Series,
    distancia_m: float,
) -> np.ndarray:
    """Fusiona ejes del mismo nombre separados por menos de `distancia_m`.

    La partición por componente conexa corta una calle cada vez que a un tramo
    intermedio le falta el tag `name`, que en OSM es común. Ese corte hay que
    deshacerlo sin fundir calles homónimas de comunas distintas.

    La distribución de distancias entre ejes homónimos del Gran Santiago
    justifica el umbral. De los 97 151 pares de ejes que comparten nombre, 8878
    están a menos de 100 metros y 10 443 a menos de 150, y de ahí la frecuencia
    decae sin cortarse: la mediana de todos los pares llega a 9.5 kilómetros. El
    pico bajo los 100 metros son cortes accidentales; la cola son calles
    distintas. Los 150 metros por defecto cubren el pico y dejan fuera la mayor
    parte de la zona ambigua.

    `ejes` y `nombres` vienen alineados con `geometrias`, una geometría por eje.
    """
    padre = {int(e): int(e) for e in ejes}

    def raiz(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    # La distancia entre dos MultiLineString es cara. Los rectángulos
    # envolventes dan una cota inferior que descarta la mayoría de los pares
    # antes de calcularla: de los 60 054 pares homónimos del Gran Santiago, la
    # mediana está sobre los diez kilómetros.
    limites = geometrias.bounds.to_numpy()
    geometrias_lista = geometrias.to_numpy()
    tabla = pd.DataFrame({"eje": ejes, "nombre": nombres.to_numpy()})

    for _, grupo in tabla[tabla["nombre"].duplicated(keep=False)].groupby("nombre"):
        indices = grupo.index.to_numpy()
        if len(indices) < 2:
            continue
        caja = limites[indices]
        for i in range(len(indices)):
            minx, miny, maxx, maxy = caja[i]
            dx = np.maximum.reduce([minx - caja[i + 1 :, 2], caja[i + 1 :, 0] - maxx, np.zeros(len(indices) - i - 1)])
            dy = np.maximum.reduce([miny - caja[i + 1 :, 3], caja[i + 1 :, 1] - maxy, np.zeros(len(indices) - i - 1)])
            candidatos = np.nonzero(np.hypot(dx, dy) < distancia_m)[0] + i + 1
            for j in candidatos:
                a, b = int(ejes[indices[i]]), int(ejes[indices[j]])
                if raiz(a) == raiz(b):
                    continue
                if geometrias_lista[indices[i]].distance(geometrias_lista[indices[j]]) < distancia_m:
                    padre[raiz(a)] = raiz(b)
    return np.array([raiz(int(e)) for e in ejes])


def _comuna_por_segmento(
    segmentos: gpd.GeoDataFrame, comunas: gpd.GeoDataFrame
) -> pd.Series:
    """Comuna que contiene el punto medio de cada segmento."""
    puntos = segmentos[["geometry"]].copy()
    puntos["geometry"] = segmentos.geometry.representative_point()
    union = gpd.sjoin(
        puntos.to_crs(config.CRS_GEOGRAFICO),
        comunas[["comuna", "geometry"]].to_crs(config.CRS_GEOGRAFICO),
        how="left",
        predicate="within",
    )
    union = union[~union.index.duplicated(keep="first")]
    return union["comuna"].reindex(segmentos.index)


def _nombrar_ejes(ejes: pd.DataFrame) -> dict[int, str]:
    """Asigna un identificador ASCII a cada eje, sin colisiones.

    Un nombre que produce un solo eje conserva su slug. Cuando produce varios,
    el identificador incorpora la comuna, y si eso tampoco alcanza se agrega un
    número. El orden es por largo descendente, así que el eje principal queda
    con el identificador más corto.
    """
    asignados: dict[int, str] = {}
    usados: set[str] = set()
    # El nombre de la columna no puede empezar con guion bajo: `itertuples` las
    # renombra a su posición y el atributo deja de existir.
    cuantos = ejes.groupby("nombre")["eje"].transform("size")
    ordenados = ejes.assign(cuantos_ejes=cuantos).sort_values(
        ["nombre", "largo_m"], ascending=[True, False]
    )
    for fila in ordenados.itertuples(index=False):
        base = identificador(fila.nombre)
        comuna = getattr(fila, "comuna", None)
        if fila.cuantos_ejes > 1 and isinstance(comuna, str) and comuna:
            base = f"{base}-{identificador(comuna)}"
        candidato = base
        sufijo = 2
        while candidato in usados:
            candidato = f"{base}-{sufijo}"
            sufijo += 1
        usados.add(candidato)
        asignados[int(fila.eje)] = candidato
    return asignados


def agregar_calles(
    segmentos: gpd.GeoDataFrame,
    comunas: gpd.GeoDataFrame | None = None,
    columna_nombre: str = "name",
    distancia_union_m: float = 150.0,
    crs_metrico: str = config.CRS_METRICO,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Agrupa los segmentos con nombre en calles.

    Parámetros
    ----------
    segmentos : salida de `grafo.partir_en_intersecciones`, con `u`, `v` y los
        tags de la way de origen.
    comunas : GeoDataFrame con una columna `comuna`. Si se entrega, cada calle
        queda etiquetada con la comuna donde está la mayor parte de sus tramos,
        y los nombres repetidos se distinguen por ella.
    columna_nombre : tag que define el nombre de la calle.
    distancia_union_m : dos ejes del mismo nombre separados por menos que esto
        se consideran la misma calle cortada por un tramo sin tag. Con 0 se
        desactiva la reunión y cada componente conexa queda como calle aparte.

    Retorna
    -------
    calles : GeoDataFrame con una fila por calle (`calle_id`, `nombre`,
        `comuna`, `largo_m`, `tipo`, `segmentos`, cobertura por modo y la
        geometría unida de sus tramos).
    segmentos : el mismo GeoDataFrame de entrada con las columnas `calle_id` y
        `comuna` agregadas (vacías en los tramos sin nombre).
    """
    con_id = segmentos.copy()
    if comunas is not None:
        con_id["comuna"] = _comuna_por_segmento(con_id, comunas)

    tiene_nombre = con_id[columna_nombre].notna().to_numpy()
    con_id["calle_id"] = None
    if not tiene_nombre.any():
        vacio = gpd.GeoDataFrame(columns=["calle_id"], geometry=[], crs=segmentos.crs)
        return vacio, con_id

    con_nombre = con_id.loc[tiene_nombre]
    codigos, _ = pd.factorize(con_nombre[columna_nombre])
    ejes = _ejes_conexos(
        con_nombre["u"].to_numpy(np.int64),
        con_nombre["v"].to_numpy(np.int64),
        codigos.astype(np.int64),
    )
    if distancia_union_m > 0:
        provisorios = gpd.GeoDataFrame(
            {"eje": ejes, "nombre": con_nombre[columna_nombre].to_numpy()},
            geometry=con_nombre.geometry.to_numpy(),
            crs=segmentos.crs,
        ).dissolve(by="eje", aggfunc={"nombre": "first"})
        unidos = _unir_ejes_cercanos(
            provisorios.index.to_numpy(),
            provisorios.to_crs(crs_metrico).geometry,
            provisorios["nombre"],
            distancia_union_m,
        )
        traduccion = dict(zip(provisorios.index.to_numpy().tolist(), unidos.tolist()))
        ejes = np.array([traduccion[int(e)] for e in ejes])

    con_id["_eje"] = pd.Series(ejes, index=con_nombre.index)

    columnas_modo = [c for c in con_id.columns if c.startswith("permite_")]
    agregaciones = {
        "nombre": (columna_nombre, "first"),
        "largo_m": ("largo_m", "sum"),
        "segmentos": ("segmento_id", "count"),
        "tipo": ("highway", lambda s: s.mode().iat[0] if not s.mode().empty else None),
    }
    if "comuna" in con_id.columns:
        agregaciones["comuna"] = (
            "comuna",
            lambda s: s.mode().iat[0] if not s.mode().empty else None,
        )
    for columna in columnas_modo:
        agregaciones[columna] = (columna, "any")

    tabla = con_id.loc[tiene_nombre].groupby("_eje").agg(**agregaciones).reset_index()
    tabla = tabla.rename(columns={"_eje": "eje"})
    nombres = _nombrar_ejes(tabla)
    tabla["calle_id"] = tabla["eje"].map(nombres)
    con_id["calle_id"] = con_id["_eje"].map(nombres)

    geometrias = con_id.loc[tiene_nombre].dissolve(by="_eje")["geometry"]
    calles = gpd.GeoDataFrame(
        tabla.merge(geometrias, left_on="eje", right_index=True).drop(columns="eje"),
        geometry="geometry",
        crs=segmentos.crs,
    )
    return calles, con_id.drop(columns="_eje")


def asignar_a_calle(
    puntos: gpd.GeoDataFrame,
    segmentos: gpd.GeoDataFrame,
    distancia_maxima_m: float = 40.0,
    crs_metrico: str = config.CRS_METRICO,
) -> pd.DataFrame:
    """Asigna cada punto a la calle con nombre más cercana.

    Los reportes ciudadanos y los puntos de interés no traen el identificador
    de la via. La asignación es geométrica: la calle con nombre cuyo eje quede
    más cerca, dentro de `distancia_maxima_m`. El umbral acota el error: un
    punto a más de esa distancia de cualquier eje con nombre queda sin
    asignar, en vez de colgarse de una calle arbitraria.

    Retorna un DataFrame indexado como `puntos`, con `calle_id`,
    `distancia_m` y `segmento_id`.
    """
    ejes = segmentos[segmentos["calle_id"].notna()]
    columnas = ["calle_id", "segmento_id", "geometry"]
    izquierda = puntos[["geometry"]].to_crs(crs_metrico)
    derecha = ejes[columnas].to_crs(crs_metrico)

    cercano = gpd.sjoin_nearest(
        izquierda,
        derecha,
        how="left",
        max_distance=distancia_maxima_m,
        distance_col="distancia_m",
    )
    # sjoin_nearest devuelve un empate por cada eje a la misma distancia.
    cercano = cercano[~cercano.index.duplicated(keep="first")]
    return cercano[["calle_id", "segmento_id", "distancia_m"]].reindex(puntos.index)


def asignar_calle(
    puntos: gpd.GeoDataFrame,
    segmentos: gpd.GeoDataFrame,
    calles: gpd.GeoDataFrame,
    distancia_maxima_m: float = 40.0,
    columna_declarada: str | None = None,
    crs_metrico: str = config.CRS_METRICO,
) -> pd.DataFrame:
    """Asigna cada punto a una calle, prefiriendo la que el propio dato declara.

    La asignación por cercanía falla en las esquinas: un local de la avenida
    puede quedar más cerca del pasaje perpendicular que del eje de la avenida.
    Cuando el punto trae una calle declarada en sus tags (`addr:street` en los
    POI de OSM) y esa calle existe en la red, se usa esa. La cercanía queda
    como criterio de respaldo.

    Retorna un DataFrame indexado como `puntos` con `calle_id`, `distancia_m`
    y `origen`, que vale `declarada` o `cercanía`.
    """
    resultado = asignar_a_calle(puntos, segmentos, distancia_maxima_m, crs_metrico)
    resultado["origen"] = np.where(resultado["calle_id"].notna(), "cercania", None)

    if columna_declarada is None or columna_declarada not in puntos.columns:
        return resultado

    por_nombre = {
        identificador(nombre): calle_id
        for nombre, calle_id in zip(calles["nombre"], calles["calle_id"])
    }
    declarada = puntos[columna_declarada].map(
        lambda valor: por_nombre.get(identificador(valor))
        if isinstance(valor, str) and valor.strip()
        else None
    )
    usar = declarada.notna()
    if not usar.any():
        return resultado

    # La distancia se recalcula contra el eje declarado: dejar la del eje más
    # cercano describiría otra calle.
    geometrias = calles.set_index("calle_id").to_crs(crs_metrico)["geometry"]
    puntos_m = puntos.geometry.to_crs(crs_metrico)
    distancias = {
        indice: float(puntos_m.loc[indice].distance(geometrias.loc[declarada.loc[indice]]))
        for indice in puntos.index[usar]
    }

    resultado.loc[usar, "calle_id"] = declarada[usar]
    resultado.loc[usar, "origen"] = "declarada"
    resultado.loc[usar, "distancia_m"] = pd.Series(distancias)
    return resultado


def cruces(segmentos: gpd.GeoDataFrame) -> pd.DataFrame:
    """Pares de calles que comparten al menos una intersección.

    Retorna `calle_a`, `calle_b` y `esquinas`, la cantidad de intersecciones
    que comparte el par. El par se ordena alfabéticamente para no registrar la
    misma relación dos veces.

    El cruce se calcula con un join de la relación intersección-calle consigo
    misma. Recorrer las intersecciones en Python daría lo mismo, pero a escala
    de ciudad son cientos de miles de grupos.
    """
    relacion = calles_por_nodo(segmentos)
    if relacion.empty:
        return pd.DataFrame(columns=["calle_a", "calle_b", "esquinas"])

    pares = relacion.merge(relacion, on="nodo_id", suffixes=("_a", "_b"))
    pares = pares[pares["calle_id_a"] < pares["calle_id_b"]]
    if pares.empty:
        return pd.DataFrame(columns=["calle_a", "calle_b", "esquinas"])

    conteo = (
        pares.groupby(["calle_id_a", "calle_id_b"])
        .size()
        .reset_index(name="esquinas")
        .rename(columns={"calle_id_a": "calle_a", "calle_id_b": "calle_b"})
    )
    return conteo


def calles_por_nodo(segmentos: gpd.GeoDataFrame) -> pd.DataFrame:
    """Relación intersección - calle, una fila por par."""
    ejes = segmentos[segmentos["calle_id"].notna()]
    relacion = pd.concat(
        [
            ejes[["u", "calle_id"]].rename(columns={"u": "nodo_id"}),
            ejes[["v", "calle_id"]].rename(columns={"v": "nodo_id"}),
        ]
    ).drop_duplicates()
    relacion["nodo_id"] = relacion["nodo_id"].astype(int)
    return relacion.reset_index(drop=True)
