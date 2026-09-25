"""Captura el visualizador de `web/` para el deck.

Sirve `web/` en un puerto local, abre las dos páginas con Chromium headless y
deja las capturas en `slides/frogql-evento/capturas/`, que se versionan porque
rehacerlas necesita un navegador. También imprime los tiempos que mide la
página de una columna, que son los que cita la lámina de cifras.

    uv run --with playwright python slides/frogql-evento/capturar-prototipo.py

La primera vez hay que bajar el navegador:

    uv run --with playwright playwright install chromium
"""

from __future__ import annotations

import functools
import http.server
import re
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
DIR_WEB = RAIZ / "web"
DESTINO = Path(__file__).resolve().parent / "capturas"
PUERTO = 8767
# El render de WebGL por software, para que deck.gl dibuje sin GPU.
ARGUMENTOS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


class Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def servir() -> http.server.ThreadingHTTPServer:
    manejador = functools.partial(Silencioso, directory=str(DIR_WEB))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", PUERTO), manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def esperar_prototipo(pagina) -> None:
    pagina.wait_for_selector(".lista button", state="attached", timeout=60_000)
    # Las teselas del mapa base llegan después que el grafo.
    pagina.wait_for_timeout(3_000)


def abrir_consulta(pagina, indice: int) -> None:
    pagina.locator(".lista button").nth(indice).click(force=True)
    pagina.wait_for_timeout(1_500)


def guardar(pagina, nombre: str, elemento: str | None = None) -> None:
    ruta = DESTINO / nombre
    if elemento:
        pagina.locator(elemento).screenshot(path=ruta)
    else:
        pagina.screenshot(path=ruta)
    print(f"  {ruta.relative_to(RAIZ)}")


def tiempos_de_la_pagina(navegador) -> None:
    """Carga la página de una columna, corre todas y lee sus tiempos."""
    pagina = navegador.new_page(viewport={"width": 1000, "height": 900})
    pagina.goto(f"http://127.0.0.1:{PUERTO}/")
    pagina.wait_for_selector("#correr-todas:not([disabled])", timeout=60_000)
    print("  cifras:", pagina.inner_text("#cifras").replace("\n", " | "))
    pagina.click("#correr-todas")
    pagina.wait_for_function("document.querySelector('#total').textContent.length > 0", timeout=60_000)
    tiempos = pagina.locator(".consulta .tiempo").all_inner_texts()
    print("  consulta 01:", tiempos[0], "| total:", pagina.inner_text("#total"))
    pagina.close()


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    servidor = servir()
    print("Capturas del visualizador:")
    with sync_playwright() as p:
        navegador = p.chromium.launch(args=ARGUMENTOS)

        # Escritorio en tema oscuro: la consulta 01 encendida sobre la comuna.
        pagina = navegador.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=2, color_scheme="dark")
        pagina.goto(f"http://127.0.0.1:{PUERTO}/prototipo/")
        esperar_prototipo(pagina)
        abrir_consulta(pagina, 0)
        guardar(pagina, "escritorio-01.png")

        # Los parámetros de la consulta 03, con un valor de la lista apagado.
        abrir_consulta(pagina, 2)
        pagina.locator(".ficha", has_text=re.compile("restaurant")).locator("input").uncheck()
        pagina.wait_for_timeout(1_500)
        guardar(pagina, "escritorio-03.png")
        guardar(pagina, "parametros-03.png", ".parametros")
        pagina.close()

        # Teléfono en tema claro, con la consulta 01 abierta.
        pagina = navegador.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=3,
            is_mobile=True, has_touch=True, color_scheme="light",
        )
        pagina.goto(f"http://127.0.0.1:{PUERTO}/prototipo/")
        esperar_prototipo(pagina)
        pagina.locator(".solo-movil").tap()
        pagina.locator(".lista button").nth(0).tap()
        pagina.wait_for_timeout(1_500)
        guardar(pagina, "movil-01.png")
        pagina.close()

        tiempos_de_la_pagina(navegador)
        navegador.close()
    servidor.shutdown()
