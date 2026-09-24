"""Prepara las figuras del deck `slides/frogql-evento/`.

Tres cosas:

- El código QR al visualizador publicado, que es lo que la sala escanea.
- Tres mapas de Independencia hechos con chiricoca a partir del grafo que
  publica el visualizador (`web/datos/independencia.json`), consultado con
  froGQL desde Python: la calle del reclamo, sus lugares y las calles a una y
  dos cuadras.
- Las capturas del visualizador, que se versionan en `capturas/` porque
  rehacerlas necesita un navegador (ver `capturar-prototipo.py`).

    uv run --with segno python slides/frogql-evento/preparar-figuras.py

`segno` genera el QR y no está entre las dependencias del proyecto, porque
sirve solo para esto. Va como dependencia pasajera de `uv run`.
"""

# %%
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import frogql
import geopandas as gpd
import matplotlib.pyplot as plt
from chiricoca.config import setup_style
from chiricoca.geo.figures import figure_from_geodataframe
from matplotlib import font_manager
from shapely.geometry import LineString

DIR_DECK = Path(__file__).resolve().parent
DIR_IMG = DIR_DECK / "img"
DIR_CAPTURAS = DIR_DECK / "capturas"
# Urbanist va con el deck, con su licencia OFL: panduck le pasa a typst el
# directorio `fonts/` que está junto al documento, y los mapas la registran de
# ahí, así que no hace falta tenerla instalada.
DIR_FUENTES = DIR_DECK / "fonts"
GRAFO = DIR_DECK.parents[1] / "web" / "datos" / "independencia.json"

SITIO = "https://zorzalerrante.github.io/frogql-case-study/prototipo/"

# Los colores del tema de las slides.
NAVY = "#0A0E50"
MAGENTA = "#CF3889"
GRIS = "#a9a9bd"

# El reclamo de la lámina de apertura, el mismo que usa el visualizador.
RECLAMO = "000000"
CALLE = "Avenida Independencia"
LOCALES_CON_ALCOHOL = ("amenity=bar", "shop=alcohol")

CAPTURAS = ("escritorio-01.png", "escritorio-03.png", "parametros-03.png", "movil-01.png")


def generar_qr() -> None:
    """Escribe el código QR al visualizador."""
    try:
        import segno
    except ImportError:
        raise SystemExit(
            "Falta segno. Correr:\n"
            "  uv run --with segno python slides/frogql-evento/preparar-figuras.py"
        )
    ruta = DIR_IMG / "qr.png"
    # Corrección de errores alta: el proyector y las fotos desde lejos comen
    # parte del código.
    segno.make(SITIO, error="h").save(ruta, scale=12, border=2, dark=NAVY)
    print(f"  {ruta.name}: {ruta.stat().st_size / 1e3:.0f} KB")


def copiar_capturas() -> None:
    faltan = [n for n in CAPTURAS if not (DIR_CAPTURAS / n).exists()]
    if faltan:
        raise SystemExit(
            f"Faltan {', '.join(faltan)} en {DIR_CAPTURAS}. Se rehacen con\n"
            "  uv run --with playwright python slides/frogql-evento/capturar-prototipo.py"
        )
    for nombre in CAPTURAS:
        shutil.copy(DIR_CAPTURAS / nombre, DIR_IMG / nombre)
        print(f"  {nombre}")


# %% [markdown]
# ## El grafo
#
# Se importa el JSON a una base temporal y se consulta con froGQL. La red se
# dibuja con los tramos entre intersecciones, igual que en el visualizador.

# %%
def abrir_grafo(directorio: str) -> frogql.Connection:
    base = str(Path(directorio) / "independencia.gdb")
    frogql.import_json(base, str(GRAFO))
    return frogql.open(base)


def tramos(conexion: frogql.Connection) -> gpd.GeoDataFrame:
    """Un tramo por par de esquinas, con la calle a la que pertenece."""
    filas = conexion.execute(
        "MATCH (a:Interseccion)-[e]-(b:Interseccion) "
        "RETURN a.lon AS x1, a.lat AS y1, b.lon AS x2, b.lat AS y2, e.calle_id AS calle",
        limit=0,
    )
    vistos = {}
    for f in filas:
        clave = tuple(sorted([(f["x1"], f["y1"]), (f["x2"], f["y2"])]))
        if clave not in vistos or vistos[clave] is None:
            vistos[clave] = f["calle"]
    return gpd.GeoDataFrame(
        {"calle": list(vistos.values())},
        geometry=[LineString(c) for c in vistos],
        crs="EPSG:4326",
    )


def ids(conexion: frogql.Connection, consulta: str) -> set[str]:
    return {f["id"] for f in conexion.execute(consulta, limit=0)}


# %% [markdown]
# ## Estilo de los mapas
#
# chiricoca fija el estilo base; encima van la tipografía y los colores del
# deck. Los mapas se guardan con fondo transparente.

# %%
def preparar_estilo() -> None:
    caras = sorted(DIR_FUENTES.glob("Urbanist-*.ttf"))
    if not caras:
        raise SystemExit(f"Falta Urbanist en {DIR_FUENTES}.")
    for cara in caras:
        font_manager.fontManager.addfont(str(cara))
    setup_style(style="white", dpi=300, font_family="Urbanist")
    plt.rcParams.update({"text.color": NAVY, "savefig.dpi": 300})


def lienzo(red: gpd.GeoDataFrame, alto: float = 3.8):
    figura, eje = figure_from_geodataframe(red, height=alto)
    red.plot(ax=eje, color=GRIS, linewidth=0.6, zorder=1)
    return figura, eje


def rotular(eje, x, y, texto, dx, dy, color=NAVY) -> None:
    eje.annotate(
        texto, (x, y), xytext=(dx, dy), textcoords="offset points",
        fontsize=11, color=color, ha="left" if dx >= 0 else "right", va="center",
        arrowprops={"arrowstyle": "-", "color": color, "lw": 0.7, "shrinkA": 2, "shrinkB": 3},
    )


def guardar(figura, nombre: str) -> None:
    ruta = DIR_IMG / nombre
    figura.savefig(ruta, bbox_inches="tight", transparent=True)
    plt.close(figura)
    print(f"  {ruta.name}")


# %% [markdown]
# ## La pregunta y la respuesta
#
# El primer mapa muestra solo el reclamo. El segundo agrega su calle y los
# lugares que cuelgan de ella, que son las filas de la consulta 01.

# %%
def mapas_del_reclamo(conexion: frogql.Connection, red: gpd.GeoDataFrame) -> None:
    reclamo = conexion.execute(
        f"MATCH (r:Reclamo) WHERE r.reporte_id = '{RECLAMO}' RETURN r.lon AS x, r.lat AS y",
        limit=0,
    )[0]
    calles = ids(
        conexion,
        "MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle) "
        f"WHERE r.reporte_id = '{RECLAMO}' RETURN c.calle_id AS id",
    )
    lugares = conexion.execute(
        "MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle)<-[:EN_CALLE]-(l:Lugar) "
        f"WHERE r.reporte_id = '{RECLAMO}' "
        "RETURN l.lon AS x, l.lat AS y, l.etiqueta AS etiqueta, l.categoria AS categoria",
        limit=0,
    )
    print(f"  reclamo {RECLAMO}: {len(calles)} calle, {len(lugares)} lugares")

    def punto_del_reclamo(eje) -> None:
        eje.scatter([reclamo["x"]], [reclamo["y"]], s=90, color=MAGENTA, edgecolor="white", linewidth=1.5, zorder=5)

    figura, eje = lienzo(red)
    punto_del_reclamo(eje)
    rotular(eje, reclamo["x"], reclamo["y"], "Reclamo en SOSAFE,\n7 de abril de 2024", 24, 26, MAGENTA)
    guardar(figura, "pregunta.png")

    figura, eje = lienzo(red)
    red[red["calle"].isin(calles)].plot(ax=eje, color=NAVY, linewidth=2, zorder=2)
    eje.scatter([l["x"] for l in lugares], [l["y"] for l in lugares], s=14, color=MAGENTA, alpha=0.5, linewidth=0, zorder=3)
    ruidosos = [l for l in lugares if l["categoria"] in ("amenity=nightclub", *LOCALES_CON_ALCOHOL)]
    eje.scatter([l["x"] for l in ruidosos], [l["y"] for l in ruidosos], s=60, color=MAGENTA, edgecolor="white", linewidth=1, zorder=4)
    punto_del_reclamo(eje)
    rotular(eje, reclamo["x"], reclamo["y"], "el reclamo", -30, -10, NAVY)
    nombres = {"amenity=nightclub": "discoteca", "shop=alcohol": "botillería"}
    # Los rótulos se reparten hacia la derecha, donde la calle deja espacio.
    for i, lugar in enumerate(sorted(ruidosos, key=lambda l: -l["y"])):
        nombre = lugar["etiqueta"] if not lugar["etiqueta"].startswith("(") else "sin nombre"
        rotular(eje, lugar["x"], lugar["y"], f"{nombre}\n{nombres[lugar['categoria']]}", 30, 20 - 30 * i, MAGENTA)
    guardar(figura, "respuesta.png")


# %% [markdown]
# ## Una y dos cuadras
#
# Las calles que cruzan a la Avenida Independencia y las que cruzan a esas,
# con los locales de la consulta de caminos.

# %%
def mapa_de_caminos(conexion: frogql.Connection, red: gpd.GeoDataFrame) -> None:
    propia = ids(conexion, f"MATCH (c:Calle) WHERE c.nombre = '{CALLE}' RETURN c.calle_id AS id")
    una = ids(
        conexion,
        f"MATCH (c:Calle)~[:CRUZA_CON]~(o:Calle) WHERE c.nombre = '{CALLE}' RETURN o.calle_id AS id",
    ) - propia
    hasta_dos = ids(
        conexion,
        f"MATCH (c:Calle)~[:CRUZA_CON]~{{1,2}}(o:Calle) WHERE c.nombre = '{CALLE}' RETURN o.calle_id AS id",
    )
    dos = hasta_dos - una - propia
    lista = ", ".join(f"'{c}'" for c in LOCALES_CON_ALCOHOL)
    locales = conexion.execute(
        f"MATCH (mi:Calle)~[:CRUZA_CON]~{{1,2}}(otra:Calle)<-[:EN_CALLE]-(l:Lugar) "
        f"WHERE mi.nombre = '{CALLE}' AND l.categoria IN [{lista}] "
        "RETURN DISTINCT l.etiqueta AS local, otra.nombre AS calle, l.lon AS x, l.lat AS y",
        limit=0,
    )
    print(f"  caminos: {len(una)} calles a una cuadra, {len(dos)} a dos, {len(locales)} filas")

    figura, eje = lienzo(red)
    red[red["calle"].isin(dos)].plot(ax=eje, color=MAGENTA, alpha=0.35, linewidth=1.3, zorder=2)
    red[red["calle"].isin(una)].plot(ax=eje, color=MAGENTA, linewidth=1.6, zorder=3)
    red[red["calle"].isin(propia)].plot(ax=eje, color=NAVY, linewidth=2.8, zorder=4)
    eje.scatter([l["x"] for l in locales], [l["y"] for l in locales], s=55, color=NAVY, edgecolor="white", linewidth=1, zorder=5)
    eje.plot([], [], color=NAVY, linewidth=2.8, label=CALLE)
    eje.plot([], [], color=MAGENTA, linewidth=1.6, label="A una cuadra")
    eje.plot([], [], color=MAGENTA, alpha=0.35, linewidth=1.3, label="A dos cuadras")
    eje.scatter([], [], s=55, color=NAVY, edgecolor="white", label="Bar o botillería")
    eje.legend(loc="lower right", frameon=False, fontsize=9, bbox_to_anchor=(0.0, 0.0))
    guardar(figura, "caminos.png")


# %%
if __name__ == "__main__":
    DIR_IMG.mkdir(parents=True, exist_ok=True)
    print("Figuras del deck:")
    generar_qr()
    copiar_capturas()

    preparar_estilo()
    with tempfile.TemporaryDirectory(dir=DIR_DECK) as directorio:
        print(f"Grafo: {GRAFO.relative_to(DIR_DECK.parents[1])}")
        conexion = abrir_grafo(directorio)
        red = tramos(conexion)
        print(f"  {len(red)} tramos dibujados")
        mapas_del_reclamo(conexion, red)
        mapa_de_caminos(conexion, red)
