"""Prepara las figuras del deck de diez láminas.

Tres cosas:

- El código QR al visualizador publicado, que es lo que la sala escanea.
- La captura de pantalla del visualizador, que se versiona porque hace falta un
  navegador para rehacerla.
- El mapa de reclamos por calle, que produce `02-caso-estudio.py` y deja en
  `salida/independencia/figuras/`.

    uv run --with segno python slides/frogql-evento/preparar-figuras.py

`segno` genera el QR y no está entre las dependencias del proyecto, porque
sirve solo para esto. Va como dependencia pasajera de `uv run`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from redosm import config  # noqa: E402

DIR_DECK = Path(__file__).resolve().parent
DIR_IMG = DIR_DECK / "img"

SITIO = "https://zorzalerrante.github.io/frogql-case-study/"

# Mapas que dibuja `02-caso-estudio.py` al construir el grafo.
PRESTADAS = ("ruido-por-calle.png",)
# Versionadas en el directorio del deck, porque necesitan un navegador.
PROPIAS = ("pantalla.png",)


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
    segno.make(SITIO, error="h").save(ruta, scale=12, border=2, dark="#0A0E50")
    print(f"  {ruta.name}: {ruta.stat().st_size / 1e3:.0f} KB")


def copiar(origen: Path, nombre: str) -> bool:
    ruta = origen / nombre
    if not ruta.exists():
        return False
    shutil.copy(ruta, DIR_IMG / nombre)
    print(f"  {nombre}")
    return True


if __name__ == "__main__":
    DIR_IMG.mkdir(parents=True, exist_ok=True)
    print("Figuras del deck:")
    generar_qr()

    faltan = [n for n in PROPIAS if not copiar(DIR_DECK, n)]
    if faltan:
        raise SystemExit(
            f"Falta {', '.join(faltan)} en {DIR_DECK}. Es una captura del "
            "visualizador y se versiona con el deck."
        )

    config.seleccionar("independencia")
    origen = config.dir_figuras()
    if not all(copiar(origen, n) for n in PRESTADAS):
        raise SystemExit(
            f"\nFaltan mapas en {origen}. Los dibuja:\n"
            "  uv run python 02-caso-estudio.py"
        )
