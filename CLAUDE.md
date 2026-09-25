# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Todo el repositorio está en español: código, docstrings, nombres de variables,
consultas y documentación. Mantener ese idioma al escribir código nuevo,
comentarios o mensajes de commit.

## Comandos

```bash
uv sync                                              # instala dependencias

uv run python 01-preparar-datos.py                   # Independencia (predeterminada)
uv run python 02-caso-estudio.py
uv run python 03-consultas.py

uv run python 01-preparar-datos.py --area santiago   # Gran Santiago
uv run python 01-preparar-datos.py --con-censo       # agrega zonas censales (descarga 758 MB)
uv run python 02-caso-estudio.py --area santiago
uv run python 03-consultas.py --area santiago

cd slides/caso-frogql && make                        # deck con panduck (perfil `slides`)
uv run python slides/figuras-slides.py               # solo las figuras del deck
```

No hay suite de pruebas ni configuración de linter. La verificación es la
corrida completa del pipeline sobre Independencia, que tarda pocos segundos.
Los scripts imprimen conteos, tiempos por etapa y comprobaciones de ida y
vuelta (por ejemplo, que el GraphML tenga tantos nodos como el grafo en
memoria).

Para explorar el grafo sin correr `03`:

```bash
frogql salida/independencia/frogql/independencia.gdb
```

### Variables de entorno

| Variable | Qué controla |
|---|---|
| `FROGQL_AREA` | Área activa cuando no se pasa `--area` |
| `FROGQL_DATOS`, `FROGQL_SALIDA`, `FROGQL_CACHE_OSM` | Rutas de datos y salidas (el Gran Santiago suma varios GB) |
| `FROGQL_DESCARGAS_PESADAS` | Equivale a `--con-censo`: autoriza las descargas grandes |
| `FROGQL_SOSAFE`, `FROGQL_ZONAS`, `FROGQL_VENUES`, `FROGQL_CHECKINS` | Rutas explícitas a cada capa de contexto |

## Arquitectura

Tres scripts numerados forman un pipeline lineal y el paquete `redosm/`
contiene la lógica. Cada script depende de las salidas del anterior:

`01-preparar-datos.py` extrae de OpenStreetMap con quackosm y deja parquet en
`datos/<área>/`. No rehace lo ya descargado: para forzar una extracción nueva
hay que borrar los parquet de `datos/<área>/osm/`. Su cuerpo vive bajo
`if __name__ == "__main__":` porque los workers de quackosm arrancan con
"spawn" y sin ese guard cada hijo reejecutaría la descarga.

`02-caso-estudio.py` construye la topología, agrega las calles, arma las tres
redes por modo, cuelga las capas de contexto, construye el grafo de propiedades
y exporta a `salida/<área>/`.

`03-consultas.py` importa el JSON en froGQL, corre los doce archivos de
`consultas/` y mide cada uno.

### El paquete `redosm/`

- `areas.py`: diccionario `AREAS` con las dos escalas. Un área es una lista de
  comunas más un `bbox` de búsqueda y un `recorte` opcional. Agregar un área es
  agregar una entrada acá.
- `config.py`: rutas por área, selección del área activa (`config.seleccionar()`
  al comienzo de cada script) y `config.resolver()`, que busca cada fuente en
  dos pasos: la variable de entorno y la descarga del dataset publicado. No
  busca en repositorios vecinos, para que el resultado no dependa de lo que haya
  en la máquina. Las fuentes marcadas `pesada` (la cartografía censal, 758 MB)
  solo se bajan con `--con-censo`.
- `descarga.py`: extracción con quackosm y resolución del límite comunal desde
  las relaciones `admin_level=8` de OSM.
- `perfiles.py`: reglas de acceso por modo, declarativas, en el diccionario
  `PERFILES`. Agregar un cuarto modo es agregar una entrada.
- `grafo.py`: `partir_en_intersecciones()` corre una sola vez sobre todas las
  ways; `grafo_desde_segmentos()` corre una vez por modo sobre esos mismos
  nodos. Esa separación es deliberada y hay que preservarla: las tres redes
  comparten numeración de nodos y por eso se pueden comparar y superponer.
- `calles.py`: identidad de la calle y asignación de puntos a calles.
- `contexto.py`: capas no viales (SOSAFE, zonas censales, venues de
  Foursquare). Sin las zonas censales el grafo se arma igual, sin nodos
  `ZonaCensal`, y la consulta `08` queda vacía.
- `propiedades.py`: arma el grafo de propiedades (seis tipos de nodo, ocho de
  arista).
- `exportar.py`: serializa a GraphML, JSON de froGQL y paquete CSV.

### El modelo de grafo

```
(:Interseccion) -[:CONECTA_AUTO]->  (:Interseccion)     dirigida, respeta oneway
(:Interseccion) ~[:CONECTA_BICI|CONECTA_PEATON]~ (:Interseccion)
(:Interseccion|:Lugar|:Reclamo|:Venue) -[:EN_CALLE]-> (:Calle)
(:Calle)        ~[:CRUZA_CON]~      (:Calle)
(:Reclamo)      -[:CERCA_DE]->      (:Lugar)
(:Lugar|:Reclamo|:Venue) -[:EN_ZONA]-> (:ZonaCensal)
(:Lugar|:Reclamo|:Venue) -[:EN_ESQUINA]-> (:Interseccion)
```

La decisión central del modelo: la calle con nombre se reifica como nodo. Con
la calle como nodo, "los lugares en la misma calle que este reclamo" es un
patrón de dos aristas y no un cálculo geométrico. Cualquier cambio que
convierta la calle en atributo rompe el argumento del caso de estudio.

`EN_CALLE` deja cada punto colgando del eje con nombre completo, que puede
medir kilómetros, así que sirve para preguntar por la calle y no por la
cercanía. `EN_ESQUINA` lo ancla además a la intersección más cercana, y desde
ahí una consulta camina la red y acota el recorrido con `sum(e.largo_m)`, que
es lo que la gente quiere decir con "a dos cuadras". Un salto de `CRUZA_CON` no
sirve para eso: une ejes enteros, y en Independencia uno de esos ejes mide tres
kilómetros.

La identidad de una calle combina el tag `name` con la conectividad: los tramos
homónimos se agrupan por componente conexa y después se vuelven a unir los ejes
separados por menos de 150 m. Agrupar solo por nombre funciona en una comuna y
falla en la ciudad.

## Restricciones que condicionan el código

- **Memoria.** Las tres exportaciones recorren los datos en vez de materializar
  el documento completo. El JSON del Gran Santiago pesa 928 MB y el pico del
  pipeline llega a 9 GB. Cualquier cambio en `exportar.py` o en `03` debe
  mantener el procesamiento por streaming, incluida la lectura por bloques del
  JSON.
- **Cargador CSV de froGQL.** La etiqueta de un nodo sale del nombre del
  archivo (`Calle.csv`, `Reclamo.csv`), y el cargador corta registros por salto
  de línea sin respetar las comillas, así que el texto libre se normaliza a una
  sola línea. El JSON no tiene esa restricción y conserva el texto original.
  Toda arista es dirigida para el CSV, así que las no dirigidas se escriben en
  los dos sentidos y el paquete declara más aristas que el JSON.
- **`limit` de `execute()`.** Es un tope de ejecución y no de presentación: con
  un valor distinto de 0 el motor deja de producir filas y el tiempo medido
  deja de corresponder a la consulta escrita. `03-consultas.py` usa `limit=0` y
  cada `.gql` declara su propio `LIMIT`.

## Consultas

Los doce archivos de `consultas/` son autocontenidos y se pegan tal cual en el
REPL. Estilo: `GROUP BY` después del `RETURN`, agrupación por la variable
cuando importa la identidad del nodo, `LIMIT` como cláusula. El encabezado de
comentarios `--` explica qué responde la consulta y por qué el patrón está
escrito así; `03-consultas.py` lo imprime, así que conviene mantenerlo.

Los archivos traen `'000050'` como identificador plantilla. `03-consultas.py`
lo sustituye por un reclamo por ruido del área activa que tenga lugares en su
calle, porque los identificadores son correlativos por área.

## Visualizador web

`web/` es una página estática que carga el grafo de Independencia en froGQL
compilado a WebAssembly y corre los doce `.gql` en el navegador. No tiene
build: `web/preparar-web.py` baja el motor de npm, copia el JSON que exporta
`02-caso-estudio.py` y junta las consultas en un archivo.

```bash
uv run python web/preparar-web.py
cd web && python3 -m http.server 8000
```

`.github/workflows/pages.yml` publica la página en GitHub Pages copiando `web/`
tal cual, sin construir nada. Por eso el grafo, el motor y las consultas están
versionados en `web/datos/` y `web/vendor/`, que es la excepción a la regla de
no versionar lo generado: publicar toma segundos y no depende de que respondan
los servidores de OpenStreetMap ni los del curso. La contraparte es que hay que
correr `preparar-web.py` y commitear el resultado cuando cambie el grafo, la
versión del motor o una consulta.

Dos restricciones del motor en el navegador condicionan la página. No hay
sistema de archivos, así que la entrada es el JSON y no el `.gdb`. Y el backend
es en RAM, así que solo entra Independencia y no el Gran Santiago, cuyo JSON
pesa 402 MB.

La versión del motor va fija en `VERSION_WASM`, dentro de `preparar-web.py`.
Hay que saltarse la 0.5.3, que hacía panic en cualquier `open_json` por leer un
reloj que el navegador no tiene.

La página detecta las etiquetas que el grafo cargado no tiene y desactiva las
consultas que las nombran, que sin `--con-censo` es la `08`.

Cada consulta se puede editar y correr modificada. En el texto original las
constantes son botones: al pulsarlas se busca el nodo al que pertenecen y se
enciende en el mapa. El vínculo se apoya en que los `.gql` del repositorio
escriben sus constantes como `variable.propiedad = 'valor'` o `IN [...]` y
declaran la etiqueta en el patrón, así que al editar el texto desaparece.

`web/grafo.js` lee del grafo la red por modo y las capas de puntos, encuentra
las constantes de cada consulta y ubica en el mapa lo que nombra un resultado.
Lo usan las dos páginas. `web/mapa.js` dibuja esa red sobre canvas y enciende
lo que nombra cada resultado. La geometría también sale de consultar el grafo: los tramos son
pares de intersecciones con `lon` y `lat`, y las tres capas de puntos son los
`Lugar`, `Reclamo` y `Venue`. Como el grafo no guarda la geometría intermedia
de cada way, una curva larga se dibuja como cuerda.

`web/prototipo/` hace lo mismo con estética de aplicación: mapa base de CARTO
en MapLibre, capas de deck.gl, bloques de HUD numerados, la consulta en una
ventana y "Acerca de" en un modal, con Space Grotesk. Tampoco tiene build:
MapLibre 4.7 y deck.gl 9.0 (bundle UMD) vienen de jsDelivr, y el grafo, el
motor y las consultas se leen de `../datos/` y `../vendor/`, así que
`preparar-web.py` alimenta las dos páginas. `tinte.js` entinta el estilo de
CARTO con los tonos del tema.

En el prototipo las consultas no se editan: `parametros.js` convierte cada
constante (`= 'x'`, `IN [...]`) y cada `LIMIT` en un parámetro, y la ventana
los muestra como controles cuyos valores posibles salen del grafo. Cada cambio
vuelve a correr la consulta. Un parámetro sobre un identificador con capa de
puntos (`Reclamo.reporte_id`) o sobre `Calle.nombre` también se llena tocando
el mapa, y al tocar un elemento sin consulta que lo reciba la lectura ofrece
las consultas que lo aceptan. Tocar una fila del resultado la enciende en el
mapa. Depende de la misma convención de escritura de los `.gql` que el
vínculo de constantes de la otra página.

En pantallas de menos de 700 px el prototipo pierde las capas de puntos y
"Correr todas", y la lista y la ventana pasan a hojas inferiores.

## Slides

`slides/caso-frogql/` es un deck compilado con panduck. `figuras-slides.py`
grafica desde `salida/<área>/tiempos-consultas.csv` y
`salida/<área>/resumen-grafo.csv`, que escriben `03` y `02`, así que las cifras
del deck son las de la última corrida. Al cambiar esas salidas hay que revisar
el script de figuras.

`slides/frogql-evento/` es el deck para público general, que remite al
prototipo con un QR. `preparar-figuras.py` hace el QR y tres mapas con
chiricoca a partir de `web/datos/independencia.json`, así que no necesita
correr el pipeline; `capturar-prototipo.py` rehace con Playwright las capturas
de `capturas/`, que se versionan, e imprime los tiempos que mide la página. El
deck trae Urbanist y Fira Code en `fonts/`, con sus licencias OFL: panduck le
pasa a typst el `fonts/` que está junto al documento y los mapas registran
Urbanist desde ahí, así que compila igual en una máquina que no las tenga
instaladas.

Las tablas del README traen las cifras de las dos escalas. Si un cambio altera
conteos, tiempos o tamaños, corresponde actualizarlas con los valores de una
corrida nueva.
