"""Genera las figuras del deck `slides/caso-frogql/`.

Se corre desde la raíz del repositorio y deja los PNG en
`slides/caso-frogql/img/`. Depende de que las dos áreas estén construidas:

    uv run python 01-preparar-datos.py [--area santiago]
    uv run python 02-caso-estudio.py   [--area santiago]
    uv run python 03-consultas.py      [--area santiago]

Los mapas de la comuna los produce `02-caso-estudio.py`; acá solo se copian.
Las demás figuras se calculan de los parquet y de los CSV de resumen.
"""

# %%
import shutil
import sys
from pathlib import Path

# El deck vive en un subdirectorio, así que hay que poner la raíz del
# repositorio en el path antes de importar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

from redosm import calles as mod_calles
from redosm import config, grafo, perfiles

NAVY = "#0A0E50"
MAGENTA = "#CF3889"
GRIS = "#c9c9d6"
DESTINO = config.RAIZ / "slides" / "caso-frogql" / "img"


# Directorios donde buscar la tipografía del tema. Matplotlib no lee las
# fuentes del usuario por su cuenta, a diferencia de fontconfig.
DIRECTORIOS_FUENTES = (
    Path.home() / ".fonts",
    Path.home() / ".local" / "share" / "fonts",
    Path("/usr/share/fonts"),
)


def registrar_fuente(familia: str = "Urbanist") -> bool:
    """Agrega a matplotlib las caras de una familia. Avisa si no la encuentra."""
    encontradas = 0
    for directorio in DIRECTORIOS_FUENTES:
        if not directorio.exists():
            continue
        for cara in directorio.rglob(f"{familia}*.[ot]tf"):
            font_manager.fontManager.addfont(str(cara))
            encontradas += 1
    if not encontradas:
        print(f"  aviso: no se encontró la tipografía {familia}, se usa la de respaldo.")
    return encontradas > 0


def preparar_estilo() -> None:
    """Registra la tipografía del tema y fija la paleta de las slides."""
    familia = "Urbanist" if registrar_fuente("Urbanist") else "DejaVu Sans"
    plt.rcParams.update(
        {
            "font.family": familia,
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "text.color": NAVY,
            "axes.labelcolor": NAVY,
            "axes.edgecolor": NAVY,
            "xtick.color": NAVY,
            "ytick.color": NAVY,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def guardar(figura, nombre: str) -> Path:
    DESTINO.mkdir(parents=True, exist_ok=True)
    ruta = DESTINO / nombre
    figura.savefig(ruta, bbox_inches="tight", transparent=True)
    plt.close(figura)
    print(f"  {ruta}")
    return ruta


def leer(area: str, archivo: str) -> pd.DataFrame:
    return pd.read_csv(config.DIR_SALIDA / area / archivo)


# %% [markdown]
# ## Los mapas de la comuna
#
# Los produce el script de análisis. Acá solo se copian al directorio del deck.

# %%
def copiar_mapas() -> None:
    origen = config.DIR_SALIDA / "independencia" / "figuras"
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre in ("redes-por-modo.png", "infraestructura-ciclista.png", "ruido-por-calle.png"):
        ruta = origen / nombre
        if ruta.exists():
            shutil.copy(ruta, DESTINO / nombre)
            print(f"  {DESTINO / nombre}")
        else:
            print(f"  falta {ruta}, corre 02-caso-estudio.py")


# %% [markdown]
# ## Distancia entre ejes que comparten nombre
#
# Justifica el umbral con que se vuelven a unir los ejes que la partición por
# componente conexa dejó separados.

# %%
def figura_ejes_homonimos() -> None:
    config.seleccionar("santiago")
    limite = gpd.read_parquet(config.dir_osm() / "limite.parquet")
    vias = gpd.read_parquet(config.dir_osm() / "vias.parquet")
    vias = pd.concat([vias, perfiles.permisos(vias)], axis=1)
    _, segmentos = grafo.partir_en_intersecciones(vias, config.area().tolerancia_nodo_m)
    ejes, _ = mod_calles.agregar_calles(segmentos, comunas=limite, distancia_union_m=0)

    metrico = ejes[ejes["nombre"].duplicated(keep=False)].to_crs(config.CRS_METRICO)
    metrico = metrico.reset_index(drop=True)
    distancias = []
    for _, grupo in metrico.groupby("nombre"):
        indices = grupo.index.to_list()
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                distancias.append(
                    metrico.geometry.iloc[indices[i]].distance(metrico.geometry.iloc[indices[j]])
                )
    serie = pd.Series(distancias)

    figura, eje = plt.subplots(figsize=(5.4, 2.9))
    eje.hist(serie[serie < 1500], bins=30, color=GRIS, edgecolor="white", linewidth=0.5)
    eje.axvline(150, color=MAGENTA, linewidth=2)
    eje.annotate(
        "150 m\numbral de reunión",
        xy=(150, eje.get_ylim()[1] * 0.72),
        xytext=(330, eje.get_ylim()[1] * 0.72),
        color=MAGENTA,
        fontsize=9,
        va="center",
    )
    eje.set_xlabel("Distancia entre dos ejes con el mismo nombre (m)")
    eje.set_ylabel("Pares de ejes")
    eje.set_title(
        f"{int((serie < 100).sum())} de los {len(serie)} pares homónimos están a menos de 100 m;\n"
        f"la mediana de todos llega a {serie.median() / 1000:.1f} km",
        fontsize=10,
        loc="left",
    )
    guardar(figura, "ejes-homonimos.png")


# %% [markdown]
# ## El tamaño del grafo en las dos escalas

# %%
def figura_escala() -> None:
    comuna = leer("independencia", "resumen-grafo.csv").set_index("etiqueta")
    ciudad = leer("santiago", "resumen-grafo.csv").set_index("etiqueta")
    tabla = pd.DataFrame(
        {"Independencia": comuna["cantidad"], "Gran Santiago": ciudad["cantidad"]}
    )
    tabla["clase"] = comuna["clase"]

    # Un solo eje en formato apaisado, que es la forma de la lámina. Con dos
    # paneles lado a lado las etiquetas del derecho invaden el izquierdo, y
    # apilados la figura queda más alta que la slide.
    nodos = tabla[tabla["clase"] == "nodo"].sort_values("Gran Santiago")
    aristas = tabla[tabla["clase"] == "arista"].sort_values("Gran Santiago")
    posiciones = list(range(len(aristas))) + list(
        range(len(aristas) + 1, len(aristas) + 1 + len(nodos))
    )
    ordenada = pd.concat([aristas, nodos])

    figura, eje = plt.subplots(figsize=(7.4, 3.8))
    eje.barh([p + 0.2 for p in posiciones], ordenada["Gran Santiago"], height=0.38, color=NAVY)
    eje.barh([p - 0.2 for p in posiciones], ordenada["Independencia"], height=0.38, color=MAGENTA)
    eje.set_yticks(posiciones)
    eje.set_yticklabels(ordenada.index, fontsize=9)
    eje.set_xscale("log")
    eje.set_xlabel("Cantidad (escala logarítmica)")
    eje.annotate(
        "Aristas", xy=(0.0, len(aristas) - 0.5), xycoords=("axes fraction", "data"),
        fontsize=10, color=NAVY, ha="left", va="center", xytext=(-88, 0),
        textcoords="offset points", weight="bold",
    )
    eje.annotate(
        "Nodos", xy=(0.0, len(aristas) + len(nodos) + 0.2), xycoords=("axes fraction", "data"),
        fontsize=10, color=NAVY, ha="left", va="center", xytext=(-88, 0),
        textcoords="offset points", weight="bold",
    )
    eje.barh([0], [0], color=NAVY, label="Gran Santiago")
    eje.barh([0], [0], color=MAGENTA, label="Independencia")
    eje.legend(frameon=False, fontsize=9, ncol=2, loc="lower right", bbox_to_anchor=(1.0, 1.0))
    guardar(figura, "escala.png")


# %% [markdown]
# ## Cuánto tarda cada consulta al cambiar de escala

# %%
ETIQUETAS_CONSULTA = {
    "01-lugares-en-la-misma-calle": "lugares en la misma calle",
    "02-ruido-por-calle": "ruido por calle",
    "03-locales-de-alcohol-en-calles-con-ruido": "locales de alcohol en calles con ruido",
    "04-cerca-pero-en-otra-calle": "cerca pero en otra calle",
    "05-calles-que-cruzan": "calles que cruzan",
    "06-ruta-entre-dos-calles": "ruta entre dos calles",
    "07-que-hay-a-pocas-cuadras": "qué hay a pocas cuadras",
    "08-vida-nocturna-que-osm-no-tiene": "vida nocturna que OSM no tiene",
    "09-ruido-en-calles-sin-comercio": "ruido en calles sin comercio",
    "10-ruido-lejos-de-la-vida-nocturna": "ruido lejos de la vida nocturna",
    "11-camino-al-local-mas-cercano": "camino al local más cercano",
    "12-vida-nocturna-de-foursquare": "vida nocturna de Foursquare",
    "13-botilleria-mas-cercana": "botillería más cercana",
}


def figura_tiempos() -> None:
    comuna = leer("independencia", "tiempos-consultas.csv").set_index("consulta")
    ciudad = leer("santiago", "tiempos-consultas.csv").set_index("consulta")
    tabla = pd.DataFrame(
        {"Independencia": comuna["milisegundos"], "Gran Santiago": ciudad["milisegundos"]}
    ).sort_values("Gran Santiago")
    etiquetas = [ETIQUETAS_CONSULTA.get(c, c.split("-", 1)[1].replace("-", " ")) for c in tabla.index]

    figura, eje = plt.subplots(figsize=(6.6, 3.6))
    posicion = range(len(tabla))
    for p, (chico, grande) in zip(posicion, tabla.itertuples(index=False)):
        eje.plot([chico, grande], [p, p], color=GRIS, linewidth=1.6, zorder=1)
    eje.scatter(tabla["Independencia"], posicion, color=MAGENTA, s=30, zorder=2, label="Independencia")
    eje.scatter(tabla["Gran Santiago"], posicion, color=NAVY, s=30, zorder=2, label="Gran Santiago")
    eje.set_yticks(list(posicion))
    eje.set_yticklabels(etiquetas, fontsize=8)
    eje.set_xscale("log")
    eje.set_xlabel("Milisegundos (escala logarítmica)")
    # Sin título: lo dice el pie de la lámina y repetirlo gasta alto.
    eje.legend(frameon=False, fontsize=9, loc="lower right")
    guardar(figura, "tiempos-consultas.png")


# %% [markdown]
# ## Qué fuente tiene la vida nocturna

# %%
NOCTURNO_FSQ = {
    "Bar", "Dive Bar", "Pub", "Nightclub", "Brewery", "Beer Garden", "Gay Bar",
    "Gastropub", "Rock Club", "Karaoke Bar", "Lounge", "Cocktail Bar", "Sports Bar",
    "Wine Bar", "Hookah Bar", "Jazz Club", "Music Venue", "Strip Club",
    "Other Nightlife", "Comedy Club", "Hotel Bar", "Whisky Bar",
}


def figura_cobertura_nocturna() -> None:
    filas = []
    for area, titulo in (("independencia", "Independencia"), ("santiago", "Gran Santiago")):
        config.seleccionar(area)
        lugares = gpd.read_parquet(config.dir_osm() / "lugares.parquet")
        venues = gpd.read_parquet(config.dir_contexto() / "venues.parquet")
        amenity = lugares["amenity"].fillna("")
        filas.append(
            {
                "area": titulo,
                "OSM bar, pub, discoteca": int(amenity.isin(["bar", "pub", "nightclub"]).sum()),
                "OSM botillerías": int((lugares["shop"].fillna("") == "alcohol").sum()),
                "Foursquare nocturnos": int(venues["category"].isin(NOCTURNO_FSQ).sum()),
            }
        )
    tabla = pd.DataFrame(filas).set_index("area")

    # Apilados por la misma razón que la figura de escala, y con una escala por
    # panel porque las dos áreas difieren en dos órdenes de magnitud.
    figura, ejes = plt.subplots(2, 1, figsize=(5.4, 3.6), sharey=True)
    for eje, (area, fila) in zip(ejes, tabla.iterrows()):
        barras = eje.barh(list(fila.index), fila.to_numpy(), color=[GRIS, NAVY, MAGENTA])
        eje.bar_label(barras, padding=4, fontsize=9, color=NAVY)
        eje.set_title(area, fontsize=11, loc="left")
        eje.set_xlim(0, fila.max() * 1.3)
        eje.set_xticks([])
        eje.tick_params(axis="y", labelsize=9)
        eje.spines["bottom"].set_visible(False)
    guardar(figura, "cobertura-nocturna.png")


# %% [markdown]
# ## La adopción de SOSAFE depende de la comuna

# %%
def figura_sesgo_sosafe() -> None:
    config.seleccionar("santiago")
    limite = gpd.read_parquet(config.dir_osm() / "limite.parquet")
    zonas = gpd.read_parquet(config.dir_contexto() / "zonas.parquet")
    reclamos = gpd.read_parquet(config.dir_contexto() / "reclamos.parquet")

    union = gpd.sjoin(
        reclamos[["geometry"]].to_crs(config.CRS_GEOGRAFICO),
        limite[["comuna", "geometry"]].to_crs(config.CRS_GEOGRAFICO),
        how="left",
        predicate="within",
    )
    por_comuna = union.groupby("comuna").size().rename("reclamos")
    poblacion = zonas.groupby("COMUNA")["n_per"].sum()
    poblacion.index = [c.title() for c in poblacion.index]
    tabla = pd.DataFrame({"reclamos": por_comuna}).join(
        pd.DataFrame({"poblacion": poblacion}), how="inner"
    )
    tabla["tasa"] = 10000 * tabla["reclamos"] / tabla["poblacion"]
    tabla = tabla.sort_values("tasa")

    figura, eje = plt.subplots(figsize=(5.2, 5.4))
    colores = [MAGENTA if c == "Independencia" else GRIS for c in tabla.index]
    eje.barh(tabla.index, tabla["tasa"], color=colores)
    eje.set_xlabel("Reclamos SOSAFE de 2024 por cada 10 mil habitantes")
    eje.tick_params(axis="y", labelsize=8)
    eje.set_title(
        f"Entre la comuna que menos reporta y la que más\n"
        f"hay un factor de {tabla['tasa'].max() / tabla['tasa'].min():.0f}",
        fontsize=10,
        loc="left",
    )
    guardar(figura, "sesgo-sosafe.png")


# %% [markdown]
# ## Cómo se asigna cada lugar a su calle

# %%
def figura_asignacion() -> None:
    filas = []
    for area, titulo in (("independencia", "Independencia"), ("santiago", "Gran Santiago")):
        config.seleccionar(area)
        limite = gpd.read_parquet(config.dir_osm() / "limite.parquet")
        lugares = gpd.read_parquet(config.dir_osm() / "lugares.parquet")
        vias = gpd.read_parquet(config.dir_osm() / "vias.parquet")
        vias = pd.concat([vias, perfiles.permisos(vias)], axis=1)
        _, segmentos = grafo.partir_en_intersecciones(vias, config.area().tolerancia_nodo_m)
        calles, segmentos = mod_calles.agregar_calles(segmentos, comunas=limite)
        asignacion = mod_calles.asignar_calle(
            lugares,
            segmentos,
            calles,
            config.area().distancia_calle_m,
            columna_declarada="addr:street",
        )
        conteo = asignacion["origen"].value_counts(dropna=False)
        filas.append(
            {
                "area": titulo,
                "Calle declarada\nen addr:street": int(conteo.get("declarada", 0)),
                "Eje con nombre\nmás cercano": int(conteo.get("cercania", 0)),
                "Sin calle\na menos de 40 m": int(asignacion["calle_id"].isna().sum()),
            }
        )
    tabla = pd.DataFrame(filas).set_index("area")
    proporcion = tabla.div(tabla.sum(axis=1), axis=0) * 100

    figura, eje = plt.subplots(figsize=(6.4, 2.2))
    izquierda = [0.0, 0.0]
    for columna, color in zip(proporcion.columns, (NAVY, MAGENTA, GRIS)):
        barras = eje.barh(proporcion.index, proporcion[columna], left=izquierda, color=color, label=columna)
        etiquetas = [
            f"{v:.0f}%" if v > 7 else "" for v in proporcion[columna]
        ]
        eje.bar_label(barras, labels=etiquetas, label_type="center", color="white", fontsize=9)
        izquierda = [a + b for a, b in zip(izquierda, proporcion[columna])]
    eje.set_xlim(0, 100)
    eje.set_xticks([])
    eje.spines["bottom"].set_visible(False)
    eje.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    eje.set_title("Origen de la calle de cada punto de interés", fontsize=11, loc="left")
    guardar(figura, "asignacion-lugares.png")


# %%
if __name__ == "__main__":
    preparar_estilo()
    print("Copiando los mapas de la comuna:")
    copiar_mapas()
    print("Generando las figuras del deck:")
    figura_escala()
    figura_tiempos()
    figura_cobertura_nocturna()
    figura_asignacion()
    figura_sesgo_sosafe()
    figura_ejes_homonimos()
    print("Listo.")
