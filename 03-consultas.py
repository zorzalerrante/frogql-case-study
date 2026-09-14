# %% [markdown]
# # Consultas GQL sobre el grafo exportado
#
# Carga el JSON exportado por `02-caso-estudio.py` en una base de froGQL y
# corre las consultas de `consultas/*.gql`. Cada archivo es autocontenido: se
# puede pegar tal cual en el REPL de froGQL.
#
#     frogql salida/independencia/frogql/independencia.gdb
#     gql> MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle) RETURN c.nombre
#
# El script mide cuánto tarda la importación y cada consulta, que es la
# comparación que interesa entre la escala de comuna y la de ciudad. También
# verifica la segunda vía de entrada, el paquete CSV.
#
#     uv run python 03-consultas.py                  # Independencia
#     uv run python 03-consultas.py --area santiago  # Gran Santiago

# %%
import time
from pathlib import Path

import frogql
import pandas as pd

from redosm import config

area = config.seleccionar()
RUTA_JSON = config.dir_frogql() / f"{area.nombre}.json"
RUTA_CSV = config.dir_frogql() / "csv"
RUTA_BASE = config.dir_frogql() / f"{area.nombre}.gdb"
DIR_CONSULTAS = config.RAIZ / "consultas"
# Filas que se imprimen de cada resultado. No acota la consulta: el tope de
# froGQL va escrito como `LIMIT` dentro de cada archivo `.gql`.
FILAS_VISIBLES = 20

pd.set_option("display.width", 140)
pd.set_option("display.max_colwidth", 60)


def cargar(ruta_json: Path, ruta_base: Path) -> tuple[frogql.Connection, float]:
    """Reconstruye la base desde el JSON y la abre.

    froGQL guarda todo en un archivo `.gdb`: datos, índices y el tipo de grafo
    inferido. Se borra antes de importar para que la base refleje siempre el
    último export.
    """
    for sufijo in ("", ".ltj"):
        candidato = Path(str(ruta_base) + sufijo)
        if candidato.exists():
            candidato.unlink()
    inicio = time.perf_counter()
    frogql.import_json(str(ruta_base), str(ruta_json))
    conexion = frogql.open(str(ruta_base))
    return conexion, time.perf_counter() - inicio


def ejecutar(conexion, consulta: str) -> tuple[pd.DataFrame, float]:
    """Corre una consulta completa y mide cuánto tarda.

    El parámetro `limit` de `execute` es un tope de ejecución y no de
    presentación: el motor deja de producir filas al alcanzarlo, así que un
    resultado truncado no se distingue de uno completo y el tiempo medido no
    corresponde a la consulta escrita. Con `limit=0` no hay tope, y cada
    archivo `.gql` declara el suyo con la cláusula `LIMIT`, que se aplica
    después de `ORDER BY`.
    """
    inicio = time.perf_counter()
    resultado = conexion.execute(consulta, limit=0)
    return pd.DataFrame(resultado), time.perf_counter() - inicio


def contar_no_dirigidas(ruta: Path, bloque: int = 8 << 20) -> int:
    """Cuenta las aristas no dirigidas del JSON leyéndolo por bloques.

    A escala de ciudad el archivo pasa de los 900 MB: cargarlo entero con
    `json.load` para contar una marca ocuparía varios gigabytes.
    """
    marca = '"directionality":"~~"'
    total = 0
    resto = ""
    with open(ruta, encoding="utf-8") as archivo:
        while trozo := archivo.read(bloque):
            texto = resto + trozo
            total += texto.count(marca)
            resto = texto[-len(marca) :]
    return total


def partir(texto: str) -> tuple[list[str], str]:
    """Separa el encabezado de comentarios del cuerpo de la consulta."""
    comentarios = [
        linea.lstrip("- ").strip()
        for linea in texto.splitlines()
        if linea.strip().startswith("--")
    ]
    consulta = "\n".join(
        linea for linea in texto.splitlines() if not linea.strip().startswith("--")
    ).strip()
    return comentarios, consulta


# %%
if not RUTA_JSON.exists():
    raise FileNotFoundError(
        f"Falta {RUTA_JSON}. Hay que correr 02-caso-estudio.py --area {area.nombre} "
        "antes que este script."
    )

print(f"Área de estudio: {area.titulo}")
print(f"JSON de entrada: {RUTA_JSON} ({RUTA_JSON.stat().st_size / 1e6:.1f} MB)")

conexion, segundos_carga = cargar(RUTA_JSON, RUTA_BASE)
print(f"Importado en {segundos_carga:.1f} s")
print(f"Base: {RUTA_BASE} ({RUTA_BASE.stat().st_size / 1e6:.1f} MB)")
print(f"Nodos: {conexion.node_count}   Aristas: {conexion.edge_count}")
esquema = conexion.schema()
print("\nEsquema inferido:")
print(f"  Nodos:   {', '.join(esquema['node_labels'])}")
print(f"  Aristas: {', '.join(esquema['edge_labels'])}")

# %% [markdown]
# ## La consulta motivadora sobre un reclamo concreto
#
# Los archivos `.gql` traen el identificador `'000050'` como plantilla. Los
# identificadores son correlativos por fecha dentro de cada área, así que el
# mismo número apunta a reportes distintos en Independencia y en el Gran
# Santiago, y en una de las dos puede caer en una calle sin lugares mapeados.
# Acá se elige uno que sí los tenga y se sustituye al correr las consultas.

# %%
PLANTILLA = "000050"

# Se elige el reclamo cuya calle tenga más lugares, y no el primero que
# aparezca: con pocos reclamos el primero suele caer en una calle con un solo
# POI y el ejemplo no muestra nada.
candidato, segundos = ejecutar(
    conexion,
    "MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle)<-[:EN_CALLE]-(l:Lugar) "
    "WHERE r.categoria = 'Ruido' "
    "RETURN r.reporte_id AS id, COUNT(l) AS lugares "
    "GROUP BY r ORDER BY lugares DESC LIMIT 1",
)
ejemplo = PLANTILLA
if candidato.empty:
    print("Ningún reclamo por ruido comparte calle con un lugar.")
else:
    ejemplo = candidato["id"].iat[0]
    detalle, _ = ejecutar(
        conexion,
        f"MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle) WHERE r.reporte_id = '{ejemplo}' "
        "RETURN r.fecha AS fecha, c.nombre AS calle, c.comuna AS comuna, "
        "r.descripcion AS descripcion LIMIT 1",
    )
    print(f"Reclamo por ruido {ejemplo} (elegido en {segundos * 1000:.0f} ms):")
    print(detalle.to_string(index=False))
    vecinos, segundos = ejecutar(
        conexion,
        f"MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle)<-[:EN_CALLE]-(l:Lugar) "
        f"WHERE r.reporte_id = '{ejemplo}' "
        f"RETURN l.etiqueta AS lugar, l.categoria AS categoria LIMIT {FILAS_VISIBLES}",
    )
    print(f"\nLugares en la misma calle [{segundos * 1000:.0f} ms]:")
    print(vecinos.to_string(index=False) if not vecinos.empty else "  (sin filas)")

# %% [markdown]
# ## Las consultas
#
# El encabezado de cada archivo explica qué responde la consulta y por qué el
# patrón está escrito así.

# %%
tiempos = {}
for ruta in sorted(DIR_CONSULTAS.glob("*.gql")):
    comentarios, consulta = partir(ruta.read_text(encoding="utf-8"))
    # Los archivos traen `PLANTILLA` como identificador de ejemplo. Acá se
    # cambia por uno que exista en el área activa y tenga lugares en su calle,
    # para que la corrida muestre resultados en las dos escalas.
    consulta = consulta.replace(f"'{PLANTILLA}'", f"'{ejemplo}'")
    resultado, segundos = ejecutar(conexion, consulta)
    tiempos[ruta.stem] = segundos

    print("=" * 78)
    print(f"{ruta.name}   [{segundos * 1000:.0f} ms]")
    for linea in comentarios:
        print(f"  {linea}")
    print("-" * 78)
    if resultado.empty:
        print("  (sin filas)")
    else:
        print(resultado.head(FILAS_VISIBLES).to_string(index=False))
        if len(resultado) > FILAS_VISIBLES:
            print(f"  ... {len(resultado)} filas en total")
    print()

# %%
medidos = pd.Series(tiempos).mul(1000).round(1).rename("milisegundos")
print(f"Tiempo por consulta ({area.titulo}, consulta completa):")
print(medidos.sort_values(ascending=False).to_string())

# Las slides del repositorio grafican estos tiempos, así que quedan en disco en
# vez de solo impresos.
ruta_tiempos = config.dir_salida() / "tiempos-consultas.csv"
medidos.rename_axis("consulta").to_csv(ruta_tiempos)
print(f"\nTiempos guardados en {ruta_tiempos}")

# %% [markdown]
# ## Verificación del paquete CSV
#
# El cargador CSV de froGQL deduce la etiqueta de cada nodo del nombre del
# archivo y trata toda arista como dirigida. Por eso el CSV trae más aristas
# que el JSON: las relaciones no dirigidas se escriben en los dos sentidos.

# %%
if RUTA_CSV.exists():
    ruta_base_csv = config.dir_frogql() / f"{area.nombre}-csv.gdb"
    for sufijo in ("", ".ltj"):
        candidato = Path(str(ruta_base_csv) + sufijo)
        if candidato.exists():
            candidato.unlink()
    inicio = time.perf_counter()
    frogql.import_csv(str(ruta_base_csv), str(RUTA_CSV))
    conexion_csv = frogql.open(str(ruta_base_csv))
    segundos_csv = time.perf_counter() - inicio

    no_dirigidas = contar_no_dirigidas(RUTA_JSON)

    comparacion = pd.DataFrame(
        {
            "json": [conexion.node_count, conexion.edge_count, round(segundos_carga, 1)],
            "csv": [
                conexion_csv.node_count,
                conexion_csv.edge_count,
                round(segundos_csv, 1),
            ],
        },
        index=["nodos", "aristas", "segundos de carga"],
    )
    print(comparacion.to_string())
    print(
        f"\nAristas no dirigidas en el JSON: {no_dirigidas}. El CSV las escribe en los "
        f"dos sentidos,\npor eso trae {conexion.edge_count + no_dirigidas} aristas. "
        f"Diferencia observada: {conexion_csv.edge_count - conexion.edge_count}."
    )

    prueba, _ = ejecutar(
        conexion_csv,
        "MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle)<-[:EN_CALLE]-(l:Lugar) "
        f"WHERE r.reporte_id = '{ejemplo}' "
        "RETURN c.nombre AS calle, l.etiqueta AS lugar LIMIT 5",
    )
    print("\nLa consulta motivadora sobre la base construida desde CSV:")
    print(prueba.to_string(index=False) if not prueba.empty else "  (sin filas)")
else:
    print(f"No hay paquete CSV en {RUTA_CSV}.")
