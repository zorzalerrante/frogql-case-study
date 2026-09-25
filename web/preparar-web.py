"""Prepara los assets del visualizador de `web/`.

Tres cosas que salen de otra parte del repositorio o de npm y que sí se
versionan, a diferencia de `datos/` y `salida/`. Son la única forma de que
GitHub Pages sirva el sitio sin construirlo: publicar es copiar `web/`.
Hay que volver a correr este script, y commitear lo que cambie, cuando se
reconstruya el grafo, se suba la versión del motor o se edite una consulta:

- `vendor/`: el motor froGQL compilado a WebAssembly, bajado del paquete npm
  `frogql-wasm`. El navegador no tiene sistema de archivos, así que el binding
  solo acepta el JSON del grafo y no el `.gdb`.
- `datos/independencia.json`: el grafo que exporta `02-caso-estudio.py`, tal
  cual. Es la misma entrada que consume `frogql.import_json` en Python.
- `datos/consultas.json`: los doce `.gql` con su encabezado de comentarios,
  en un solo archivo para que la página haga una descarga y no doce.

    uv run python web/preparar-web.py

La versión del motor va fija para que la página no cambie de motor sin que
nadie lo decida. Conviene saltarse la 0.5.3, que hacía panic en cualquier
`open_json` por leer un reloj que el navegador no tiene; la 0.5.4 lo arregla.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redosm import config  # noqa: E402

VERSION_WASM = "0.5.9"
URL_WASM = f"https://registry.npmjs.org/frogql-wasm/-/frogql-wasm-{VERSION_WASM}.tgz"
ARCHIVOS_WASM = ("frogql_wasm.js", "frogql_wasm_bg.wasm")

DIR_WEB = Path(__file__).resolve().parent
DIR_VENDOR = DIR_WEB / "vendor"
DIR_DATOS = DIR_WEB / "datos"


def vendorizar_motor() -> None:
    """Baja el paquete npm y deja los dos archivos que usa la página.

    Vuelve a bajarlo cuando cambia `VERSION_WASM`, que es lo que dice el
    archivo `VERSION` que queda junto a los binarios.
    """
    marca = DIR_VENDOR / "VERSION"
    vigente = marca.read_text(encoding="utf-8").strip() if marca.exists() else None
    if vigente == VERSION_WASM and all((DIR_VENDOR / n).exists() for n in ARCHIVOS_WASM):
        print(f"Motor {VERSION_WASM} ya vendorizado en {DIR_VENDOR}")
        return
    DIR_VENDOR.mkdir(parents=True, exist_ok=True)
    print(f"Bajando frogql-wasm {VERSION_WASM} de npm")
    with urllib.request.urlopen(URL_WASM) as respuesta:
        paquete = io.BytesIO(respuesta.read())
    with tarfile.open(fileobj=paquete, mode="r:gz") as tar:
        for nombre in ARCHIVOS_WASM:
            miembro = tar.extractfile(f"package/{nombre}")
            if miembro is None:
                raise FileNotFoundError(f"El paquete no trae {nombre}.")
            destino = DIR_VENDOR / nombre
            destino.write_bytes(miembro.read())
            print(f"  {destino.name}: {destino.stat().st_size / 1e6:.1f} MB")
    (DIR_VENDOR / "VERSION").write_text(f"{VERSION_WASM}\n", encoding="utf-8")


def copiar_grafo() -> int:
    """Copia el JSON del grafo y devuelve su tamaño en bytes."""
    origen = config.dir_frogql() / f"{config.area().nombre}.json"
    if not origen.exists():
        raise SystemExit(
            f"Falta {origen}. Hay que correr 01-preparar-datos.py y "
            "02-caso-estudio.py antes de preparar la página."
        )
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    destino = DIR_DATOS / "independencia.json"
    shutil.copyfile(origen, destino)
    print(f"  {destino.name}: {destino.stat().st_size / 1e6:.1f} MB")
    return destino.stat().st_size


def juntar_consultas() -> int:
    """Escribe los doce `.gql` en un solo JSON, con su encabezado aparte.

    El motor acepta los comentarios `--` dentro del texto, así que la consulta
    se manda tal cual. El encabezado se separa igual para mostrarlo como
    explicación en la página.
    """
    consultas = []
    for ruta in sorted((config.RAIZ / "consultas").glob("*.gql")):
        texto = ruta.read_text(encoding="utf-8")
        encabezado = [
            linea.lstrip("- ").strip()
            for linea in texto.splitlines()
            if linea.strip().startswith("--")
        ]
        cuerpo = "\n".join(
            linea for linea in texto.splitlines() if not linea.strip().startswith("--")
        ).strip()
        # La primera línea del encabezado es la pregunta que responde la
        # consulta, escrita como oración. Sirve de título mejor que el nombre
        # del archivo, que va sin acentos. El resto es el porqué del patrón, y
        # se junta en un párrafo porque viene cortado a 79 columnas.
        numero = ruta.stem.partition("-")[0]
        consultas.append(
            {
                "archivo": ruta.name,
                "numero": numero,
                "titulo": encabezado[0].rstrip(".") if encabezado else ruta.stem,
                "explicacion": " ".join(encabezado[1:]),
                "gql": cuerpo,
            }
        )
    destino = DIR_DATOS / "consultas.json"
    destino.write_text(
        json.dumps(consultas, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"  {destino.name}: {len(consultas)} consultas")
    return len(consultas)


if __name__ == "__main__":
    config.seleccionar("independencia")
    vendorizar_motor()
    print("Assets del grafo:")
    copiar_grafo()
    juntar_consultas()
    print(
        "\nListo. Para servir la página:\n"
        "  cd web && python3 -m http.server 8000\n"
        "y abrir http://localhost:8000\n"
        "\nLo que cambie en web/datos/ y web/vendor/ hay que commitearlo: "
        "GitHub Pages\npublica el directorio tal cual, sin construir nada."
    )
