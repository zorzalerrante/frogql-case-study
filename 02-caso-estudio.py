# %% [markdown]
# # Redes viales como grafo de propiedades
#
# Las mismas calles producen redes distintas según quien circule. La Autopista
# Central conecta el norte de Santiago para un auto y es una barrera para quien
# camina; un paseo peatonal funciona al revés. Este script construye las tres
# redes del área de estudio sobre el mismo conjunto de intersecciones, les
# cuelga tres capas de contexto (reclamos ciudadanos de SOSAFE, puntos de
# interés de OSM, zonas censales) y exporta el resultado en tres formatos.
#
# La pregunta que motiva el modelo es relacional: dado un reclamo por ruido,
# qué lugares están en la misma calle. Responderla con geometría exige un
# buffer y un criterio de distancia; responderla sobre un grafo de propiedades
# es recorrer dos aristas. Por eso la calle con nombre se reifica como nodo.
#
# El mismo código corre sobre dos escalas:
#
#     uv run python 02-caso-estudio.py                  # Independencia
#     uv run python 02-caso-estudio.py --area santiago  # Gran Santiago
#
# Antes de correr este script hay que correr `01-preparar-datos.py`.

# %%
import time

import geopandas as gpd
import pandas as pd

from redosm import calles as mod_calles
from redosm import config, exportar, grafo, perfiles, propiedades

area = config.seleccionar()
config.crear_directorios()
pd.set_option("display.width", 120)

etapas: dict[str, float] = {}
_marca = time.perf_counter()


def cronometrar(nombre: str) -> None:
    """Registra cuánto tardó la etapa que acaba de terminar."""
    global _marca
    ahora = time.perf_counter()
    etapas[nombre] = ahora - _marca
    _marca = ahora
    print(f"  [{etapas[nombre]:.1f} s] {nombre}")


print(f"Área de estudio: {area.titulo} ({len(area.comunas)} comunas)")

# %% [markdown]
# ## Parte 1. Qué trae OpenStreetMap
#
# OSM modela las calles como *ways*: secuencias ordenadas de coordenadas con
# tags. Los tags no describen la geometría sino el uso, y de ahí salen las
# reglas de acceso por modo. Un mismo way puede admitir autos, bicicletas y
# peatones, o solo uno de los tres.

# %%
limite = gpd.read_parquet(config.dir_osm() / "limite.parquet")
vias = gpd.read_parquet(config.dir_osm() / "vias.parquet")
area_km2 = limite.to_crs(config.CRS_METRICO).area.sum() / 1e6

print(f"{area.titulo}: {area_km2:.1f} km^2 en {len(limite)} comunas")
print(f"Ways con tag highway: {len(vias)}")
print("\nClasificación vial (tag highway):")
print(vias["highway"].value_counts().head(12).to_string())
cronometrar("cargar vías")

# %%
# Reglas de acceso por modo. Cada columna `permite_*` dice si ese modo puede
# circular por el way, según highway, los tags de acceso y el tipo de servicio.
vias = pd.concat([vias, perfiles.permisos(vias)], axis=1)
vias["sentido"] = perfiles.sentido(vias)
vias["ciclovia"] = perfiles.tiene_ciclovia(vias)

print("Ways habilitados por modo:")
for nombre, perfil in perfiles.PERFILES.items():
    habilitados = int(vias[f"permite_{nombre}"].sum())
    print(
        f"  {nombre:7s} {habilitados:7d} de {len(vias)} "
        f"({habilitados / len(vias):.0%})  {perfil.descripcion}"
    )

print(f"\nSentido de circulación:\n{vias['sentido'].value_counts().to_string()}")
propias = int((vias["highway"] == "cycleway").sum())
print(f"\nWays con infraestructura ciclista declarada: {int(vias['ciclovia'].sum())}")
print(f"  Como way propia (highway=cycleway): {propias}")
print(
    "  Como atributo de la calzada (cycleway:left, cycleway:right): "
    f"{int(vias['ciclovia'].sum()) - propias}"
)
cronometrar("reglas de acceso")

# %% [markdown]
# ## Parte 2. De ways a topología
#
# Una way puede atravesar varias esquinas sin declararlas, y dos calles que se
# cruzan comparten la coordenada pero no un identificador. Para obtener un
# grafo hay que agrupar coordenadas coincidentes en nodos y cortar cada way en
# los nodos que comparte con otras. Sin ese corte, una avenida que cruza diez
# esquinas queda como una sola arista.
#
# La partición corre una vez sobre todas las ways. Las tres redes por modo son
# después subconjuntos de los mismos segmentos, sobre los mismos nodos, lo que
# permite compararlas y superponerlas.

# %%
nodos, segmentos = grafo.partir_en_intersecciones(
    vias, tolerancia_metros=area.tolerancia_nodo_m
)
print(f"Intersecciones: {len(nodos)}")
print(f"Segmentos entre intersecciones: {len(segmentos)}")
print(f"Largo total: {segmentos['largo_m'].sum() / 1000:.1f} km")
print(f"Largo mediano de un segmento: {segmentos['largo_m'].median():.0f} m")
cronometrar("partición en intersecciones")

# %%
# Los segmentos que comparten el tag `name` forman una calle. La calle es la
# unidad que usa una persona para ubicarse, y la que necesitan las consultas.
calles, segmentos = mod_calles.agregar_calles(segmentos, comunas=limite)
con_nombre = int(segmentos["calle_id"].notna().sum())

print(f"Calles con nombre: {len(calles)}")
print(f"Segmentos asignados a una calle: {con_nombre} de {len(segmentos)}")
print(f"Segmentos sin nombre en OSM: {len(segmentos) - con_nombre}")
columnas_calle = [c for c in ("nombre", "comuna", "tipo", "largo_m", "segmentos") if c in calles]
print("\nCalles de mayor extensión:")
print(
    calles.nlargest(10, "largo_m")[columnas_calle]
    .assign(largo_m=lambda d: d["largo_m"].round(0))
    .to_string(index=False)
)
print(
    "\nEl largo suma las dos calzadas cuando la avenida está mapeada como dos"
    "\nways paralelos, que es la convención de OSM para vías segregadas."
)
cronometrar("agregación en calles")

# %% [markdown]
# ## Parte 3. Las tres redes
#
# El grafo de autos es dirigido y respeta `oneway`: una calle de doble sentido
# aporta dos arcos y una de sentido único aporta uno. Los grafos de bicicleta y
# peatones son no dirigidos. Para que las cifras sean comparables, el largo y
# el grado medio se calculan sobre tramos distintos y no sobre arcos.

# %%
redes = {}
for nombre, perfil in perfiles.PERFILES.items():
    permitidos = segmentos[segmentos[f"permite_{nombre}"]]
    redes[nombre] = grafo.grafo_desde_segmentos(
        nodos, permitidos, dirigido=perfil.dirigido, columna_sentido="sentido"
    )

comparacion = grafo.tabla_resumen({n: grafo.resumen(g) for n, g in redes.items()})
print("Comparación de las tres redes:")
print(comparacion.round(3).to_string())
print(
    "\n`cobertura_gcc` es la fracción de nodos en la componente conexa mayor."
    "\nUn valor bajo indica una red fragmentada: tramos que existen pero que"
    "\nno se alcanzan desde el resto sin cambiar de modo."
)

# La red peatonal es la más fragmentada de las tres. Sus componentes aisladas
# son pasarelas, escaleras y pasajes interiores que OSM mapea sin conectar con
# la vereda de la calle.
peatonal = redes["peaton"]
gigante = grafo.componente_gigante(peatonal)
print(
    f"\nRed peatonal: {peatonal.number_of_nodes()} nodos, de los cuales "
    f"{gigante.number_of_nodes()} están en la componente mayor."
)
cronometrar("redes por modo")

# %%
if area.figuras:
    from chiricoca.config import setup_style
    from chiricoca.geo.figures import (
        figure_from_geodataframe,
        small_multiples_from_geodataframe,
    )
    from matplotlib.colors import PowerNorm

    setup_style(dpi=128)

    figura, ejes = small_multiples_from_geodataframe(limite, 3, height=4.5, col_wrap=3)
    for eje, (nombre, perfil) in zip(ejes, perfiles.PERFILES.items()):
        limite.plot(ax=eje, color="#f2f2f2", edgecolor="#bdbdbd", linewidth=0.8)
        segmentos[segmentos[f"permite_{nombre}"]].plot(ax=eje, color="#0A0E50", linewidth=0.5)
        resumen = grafo.resumen(redes[nombre])
        eje.set_title(
            f"{perfil.descripcion}\n{resumen['km']:.0f} km, "
            f"{resumen['nodos']} intersecciones"
        )
    ruta_figura = config.dir_figuras() / "redes-por-modo.png"
    figura.savefig(ruta_figura, bbox_inches="tight")
    print(f"Figura guardada en {ruta_figura}")

    # La red ciclista habilitada y la infraestructura dedicada no coinciden: por
    # la mayoría de las calles residenciales se puede pedalear, pero solo una
    # parte tiene ciclovía o banda demarcada.
    habilitada = segmentos[segmentos["permite_bici"]]
    dedicada = segmentos[segmentos["ciclovia"]]
    figura, eje = figure_from_geodataframe(limite, height=6)
    limite.plot(ax=eje, color="#f7f7f7", edgecolor="#bdbdbd", linewidth=0.8)
    habilitada.plot(ax=eje, color="#c9c9d6", linewidth=0.6)
    dedicada.plot(ax=eje, color="#CF3889", linewidth=1.8)
    eje.set_title(
        f"Red ciclista habilitada ({habilitada['largo_m'].sum() / 1000:.0f} km)"
        f" e infraestructura dedicada ({dedicada['largo_m'].sum() / 1000:.1f} km)"
    )
    ruta_figura = config.dir_figuras() / "infraestructura-ciclista.png"
    figura.savefig(ruta_figura, bbox_inches="tight")
    print(f"Figura guardada en {ruta_figura}")
else:
    habilitada = segmentos[segmentos["permite_bici"]]
    dedicada = segmentos[segmentos["ciclovia"]]

print(
    f"Infraestructura dedicada: {dedicada['largo_m'].sum() / 1000:.1f} km sobre "
    f"{habilitada['largo_m'].sum() / 1000:.0f} km habilitados"
)
cronometrar("figuras de red")

# %% [markdown]
# ## Parte 4. Lo que ocurre sobre la red
#
# Tres capas se cuelgan de las calles. Los reclamos de SOSAFE son reportes
# ciudadanos georreferenciados; los lugares son puntos de interés de OSM con
# nombre propio; las zonas censales aportan la población que vive alrededor.
# Ninguna trae el identificador de la vía, así que la asignación es
# geométrica: la calle con nombre más cercana dentro de un umbral.
#
# Un punto de interés entra al grafo si tiene nombre propio o si su categoría
# no es mobiliario urbano ni equipamiento de parcela privada. Exigir nombre
# dejaría fuera comercio real, que es lo que interesa para cruzar con los
# reclamos.

# %%
lugares = gpd.read_parquet(config.dir_osm() / "lugares.parquet")
reclamos = gpd.read_parquet(config.dir_contexto() / "reclamos.parquet")
ruta_zonas = config.dir_contexto() / "zonas.parquet"
ruta_venues = config.dir_contexto() / "venues.parquet"
zonas = gpd.read_parquet(ruta_zonas) if ruta_zonas.exists() else None
venues = gpd.read_parquet(ruta_venues) if ruta_venues.exists() else None

con_nombre_osm = int(lugares["name"].notna().sum())
print(
    f"Puntos de interés: {len(lugares)} "
    f"({con_nombre_osm} con nombre en OSM, {len(lugares) - con_nombre_osm} sin él)"
)
print(f"Reclamos SOSAFE: {len(reclamos)}")
print(f"  Periodo: {reclamos['fecha'].min()} a {reclamos['fecha'].max()}")
print(f"Zonas censales: {0 if zonas is None else len(zonas)}")
print(f"Venues de Foursquare: {0 if venues is None else len(venues)}")
print("\nReclamos por categoría:")
print(reclamos["categoria"].value_counts().head(8).to_string())
cronometrar("cargar capas de contexto")

# %%
# La asignación geométrica se puede auditar contra los propios datos: parte de
# los lugares declara su calle en el tag `addr:street`. Comparar ese valor con
# la calle más cercana mide el error del criterio de distancia.
geometrica = mod_calles.asignar_a_calle(lugares, segmentos, area.distancia_calle_m)
auditoria = (
    lugares[["name", "addr:street"]]
    .join(geometrica)
    .merge(
        calles[["calle_id", "nombre"]].rename(columns={"nombre": "calle_cercana"}),
        on="calle_id",
        how="left",
    )
)
declarados = auditoria.dropna(subset=["addr:street", "calle_cercana"])
coincide = declarados["addr:street"].str.strip() == declarados["calle_cercana"].str.strip()

print(
    f"Lugares asignados por cercanía: {int(geometrica['calle_id'].notna().sum())} "
    f"de {len(lugares)}"
)
print(f"Distancia mediana al eje más cercano: {geometrica['distancia_m'].median():.1f} m")
print(f"\nLugares que declaran addr:street: {len(declarados)}")
print(f"La calle más cercana es la declarada en {coincide.mean():.1%} de los casos")
print(
    "\nEl desacuerdo se concentra en las esquinas: un local de la avenida puede"
    "\nquedar más cerca del pasaje perpendicular que del eje de la avenida."
)

# Por eso la asignación definitiva prefiere la calle declarada cuando existe en
# la red, y deja la cercanía como respaldo. El grafo exportado registra en cada
# arista EN_CALLE cuál de los dos criterios se usó.
asignacion = mod_calles.asignar_calle(
    lugares, segmentos, calles, area.distancia_calle_m, columna_declarada="addr:street"
)
print("\nOrigen de la asignación de los lugares:")
print(asignacion["origen"].value_counts(dropna=False).to_string())
cronometrar("auditoría de la asignación")

# %%
# Reclamos de ruido por calle. El conteo usa la misma asignación geométrica.
asignacion_reclamos = mod_calles.asignar_a_calle(reclamos, segmentos, area.distancia_calle_m)
reclamos_calle = reclamos[["categoria"]].join(asignacion_reclamos)
ruido = reclamos_calle[reclamos_calle["categoria"] == "Ruido"]
conteo_ruido = ruido["calle_id"].value_counts().rename("reclamos_ruido")

calles_ruido = calles.join(conteo_ruido, on="calle_id")
calles_ruido["reclamos_ruido"] = calles_ruido["reclamos_ruido"].fillna(0).astype(int)
calles_ruido["ruido_por_km"] = calles_ruido["reclamos_ruido"] / (calles_ruido["largo_m"] / 1000)

print(f"Reclamos por ruido: {len(ruido)} ({len(ruido) / len(reclamos):.0%} del total)")
print(f"Asignados a una calle: {int(ruido['calle_id'].notna().sum())}")
print("\nCalles con más reclamos por ruido:")
print(
    calles_ruido.nlargest(10, "reclamos_ruido")[
        columnas_calle[:-2] + ["reclamos_ruido", "ruido_por_km"]
    ]
    .round({"ruido_por_km": 1})
    .to_string(index=False)
)

if area.figuras:
    figura, eje = figure_from_geodataframe(limite, height=6.5)
    limite.plot(ax=eje, color="#f7f7f7", edgecolor="#bdbdbd", linewidth=0.8)
    calles_ruido[calles_ruido["reclamos_ruido"] == 0].plot(ax=eje, color="#d9d9d9", linewidth=0.5)
    con_reclamos = calles_ruido[calles_ruido["reclamos_ruido"] > 0]
    maximo = con_reclamos["reclamos_ruido"].max()
    # La distribución es muy asimétrica: unas pocas calles concentran la mayoría
    # de los reclamos. Con escala lineal el resto queda en el extremo claro de
    # la paleta, así que se usa raíz cuadrada para separar los valores medios.
    con_reclamos.plot(
        ax=eje,
        column="reclamos_ruido",
        cmap="magma_r",
        norm=PowerNorm(0.5, vmin=1, vmax=maximo),
        linewidth=1.0 + 3.0 * con_reclamos["reclamos_ruido"] / maximo,
        legend=True,
        legend_kwds={"label": "Reclamos por ruido en 2024", "shrink": 0.6},
    )
    eje.set_title(f"Reclamos por ruido por calle, {area.titulo}")
    ruta_figura = config.dir_figuras() / "ruido-por-calle.png"
    figura.savefig(ruta_figura, bbox_inches="tight")
    print(f"Figura guardada en {ruta_figura}")
cronometrar("reclamos por calle")

# %% [markdown]
# ## Parte 5. El grafo de propiedades
#
# Seis tipos de nodo y siete de arista. La calle con nombre es nodo, no
# atributo, y por eso cualquier par de entidades que compartan calle queda a
# dos aristas de distancia.

# %%
print("Construyendo el grafo de propiedades:")
grafo_propiedades = propiedades.construir(
    nodos,
    segmentos,
    calles,
    lugares,
    reclamos,
    zonas=zonas,
    venues=venues,
    distancia_calle_m=area.distancia_calle_m,
    distancia_cercania_m=area.distancia_cercania_m,
)

print("\nNodos por etiqueta:")
print(grafo_propiedades.conteo_nodos().to_string())
print("\nAristas por etiqueta:")
print(grafo_propiedades.conteo_aristas().to_string())
print(
    f"\nTotal: {len(grafo_propiedades.nodos)} nodos, "
    f"{len(grafo_propiedades.aristas)} aristas"
)

# Las slides del repositorio grafican estos conteos, así que quedan en disco en
# vez de solo impresos.
resumen_grafo = pd.concat(
    [
        grafo_propiedades.conteo_nodos().rename("cantidad").to_frame().assign(clase="nodo"),
        grafo_propiedades.conteo_aristas().rename("cantidad").to_frame().assign(clase="arista"),
    ]
)
ruta_resumen = config.dir_salida() / "resumen-grafo.csv"
resumen_grafo.rename_axis("etiqueta").to_csv(ruta_resumen)
print(f"Resumen guardado en {ruta_resumen}")
cronometrar("grafo de propiedades")

# %% [markdown]
# ## Parte 6. Exportación
#
# Tres formatos para tres usos. GraphML es el formato de intercambio que leen
# NetworkX, igraph, Gephi y Cytoscape, y se escribe una vez por modo más una
# con el grafo completo. El JSON y el paquete CSV son las dos vías de entrada
# de froGQL; el JSON conserva la direccionalidad por arista y el CSV la pierde,
# porque su cargador trata toda arista como dirigida.

# %%
salidas = {}
print("GraphML por modo:")
for nombre, red in redes.items():
    ruta = exportar.exportar_red(red, config.dir_grafos() / f"red-{nombre}.graphml")
    salidas[ruta.name] = ruta.stat().st_size
    print(f"  {ruta.name}: {ruta.stat().st_size / 1e6:.1f} MB")
cronometrar("GraphML por modo")

ruta = exportar.exportar_grafo_propiedades(
    grafo_propiedades, config.dir_grafos() / f"{area.nombre}.graphml"
)
salidas[ruta.name] = ruta.stat().st_size
print(f"\nGraphML del grafo completo:\n  {ruta.name}: {ruta.stat().st_size / 1e6:.1f} MB")
cronometrar("GraphML completo")

ruta_json = exportar.exportar_frogql_json(
    grafo_propiedades, config.dir_frogql() / f"{area.nombre}.json"
)
salidas[ruta_json.name] = ruta_json.stat().st_size
print(f"\nJSON para froGQL:\n  {ruta_json}: {ruta_json.stat().st_size / 1e6:.1f} MB")
cronometrar("JSON de froGQL")

ruta_csv = exportar.exportar_frogql_csv(grafo_propiedades, config.dir_frogql() / "csv")
archivos_csv = sorted(ruta_csv.glob("*.csv"))
salidas["csv/"] = sum(p.stat().st_size for p in archivos_csv)
print(f"\nPaquete CSV para froGQL en {ruta_csv}:")
print(f"  {len(archivos_csv)} archivos, {salidas['csv/'] / 1e6:.1f} MB")
cronometrar("CSV de froGQL")

# %%
# Verificación de ida y vuelta sobre el GraphML por modo. Se cuentan las
# etiquetas del XML en vez de cargarlo con NetworkX, que a escala de ciudad
# tardaría más que escribirlo.
ruta_auto = config.dir_grafos() / "red-auto.graphml"
texto = ruta_auto.read_text(encoding="utf-8")
print(
    f"red-auto.graphml: {texto.count('<node ')} nodos, {texto.count('<edge ')} aristas"
)
print(
    "Coincide con el grafo en memoria: "
    f"{texto.count('<node ') == redes['auto'].number_of_nodes()} "
    f"y {texto.count('<edge ') == redes['auto'].number_of_edges()}"
)
del texto

# %%
resumen_escala = pd.Series(etapas).rename("segundos").to_frame()
resumen_escala["porcentaje"] = 100 * resumen_escala["segundos"] / resumen_escala["segundos"].sum()
print(f"\nTiempo por etapa ({area.titulo}):")
print(resumen_escala.round(1).to_string())
print(f"Total: {resumen_escala['segundos'].sum():.0f} s")

print("\nTamaño de las salidas:")
for nombre, tamano in sorted(salidas.items(), key=lambda t: -t[1]):
    print(f"  {nombre:28s} {tamano / 1e6:8.1f} MB")

print("\nExportación terminada. El paso siguiente es 03-consultas.py.")
