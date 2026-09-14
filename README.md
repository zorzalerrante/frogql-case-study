# Redes viales de OpenStreetMap como grafo de propiedades para froGQL

Este repositorio construye las redes viales de un área de Santiago a partir de
OpenStreetMap, una por modo de transporte, y las exporta como grafo de
propiedades para consultarlas con [froGQL](https://github.com/pleiad/frogql),
una base de datos de grafos que implementa ISO GQL. Sobre esas redes cuelga
tres capas de contexto: los reclamos ciudadanos de SOSAFE, los puntos de
interés de OSM y las zonas censales del Censo 2024.

El mismo código corre sobre dos escalas. La comuna de Independencia sirve para
entender el modelo leyendo los datos a ojo. El Gran Santiago, 34 comunas y 460 mil
nodos, sirve para medir cómo escalan la construcción, la exportación y las
consultas.

La pregunta que motiva el modelo es relacional: dado un reclamo por ruido, qué
lugares están en la misma calle. Responderla con geometría exige un buffer y un
criterio de distancia en cada consulta. Con la calle con nombre reificada como
nodo del grafo, es un patrón de dos aristas:

```gql
MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle)<-[:EN_CALLE]-(l:Lugar)
WHERE r.reporte_id = '000050'
RETURN c.nombre AS calle, l.etiqueta AS lugar, l.categoria AS categoria
```

```
    calle                                                             lugar
Escanilla Departamento de Encargo y Búsqueda de Personas y Vehículos (SEBV)
Escanilla                                                             Os 10
Escanilla                                          El Señor de Los Milagros
Escanilla                                                       Mi Chimbote
```

## Las dos escalas

| | Independencia | Gran Santiago |
|---|---|---|
| Comunas | 1 | 34 |
| Superficie | 7.3 km^2 | 1145.4 km^2 |
| Ways de OSM con `highway` | 1683 | 183 797 |
| Intersecciones | 2610 | 288 825 |
| Segmentos entre intersecciones | 3551 | 413 831 |
| Largo de la red | 185 km | 21 835 km |
| Calles (ejes con nombre) | 325 | 38 427 |
| Puntos de interés | 675 | 45 613 |
| Reclamos SOSAFE | 226 | 21 880 |
| Zonas censales | 26 | 1639 |
| Venues de Foursquare | 822 | 64 382 |
| **Nodos del grafo** | **4684** | **460 766** |
| **Aristas del grafo** | **15 608** | **1 687 173** |

El Gran Santiago se define como las 32 comunas de la Provincia de Santiago más
Puente Alto y San Bernardo, recortadas al rectángulo que el curso de datos
geográficos usa para todos sus datasets urbanos
(`gdsutils.ndvi.BBOX_SANTIAGO`). El recorte importa por dos razones. Varias de
esas comunas se extienden mucho más allá del área urbana continua, y Lo
Barnechea llega hasta la frontera con Argentina: sin recorte el área pasa de
1145 a 2270 km^2, casi el doble, mientras la red crece 5% (de 21 832 a 22 994
km) porque lo que se agrega es cordillera. Y los reportes SOSAFE del curso ya
vienen recortados a ese mismo rectángulo desde el origen, así que usarlo
mantiene alineadas la red y las capas de contexto.

Las tres redes viales sobre el mismo conjunto de intersecciones:

| Área | Modo | Intersecciones | Tramos | Arcos | Largo | Componentes | Componente mayor |
|---|---|---|---|---|---|---|---|
| Independencia | Auto | 1847 | 2397 | 3527 | 143 km | 4 | 99.6% |
| Independencia | Bicicleta | 1829 | 2400 | 2400 | 138 km | 8 | 98.1% |
| Independencia | Peatón | 2220 | 2931 | 2931 | 147 km | 10 | 91.6% |
| Gran Santiago | Auto | 197 899 | 250 155 | 420 994 | 13 013 km | 328 | 99.0% |
| Gran Santiago | Bicicleta | 202 332 | 257 392 | 257 392 | 13 691 km | 621 | 98.3% |
| Gran Santiago | Peatón | 243 866 | 342 921 | 342 921 | 16 862 km | 1007 | 97.9% |

La red de autos es dirigida y respeta `oneway`, por eso tiene más arcos que
tramos. Las otras dos son no dirigidas. El largo y el grado medio se calculan
sobre tramos distintos y no sobre arcos, para que las cifras sean comparables
entre modos.

## Escala

El pipeline completo del Gran Santiago tarda menos de cuatro minutos y cabe en
siete gigabytes de memoria. Las mediciones son de una máquina con 20 núcleos y
62 GB de RAM, con los datos en disco local y el extracto PBF ya descargado.

| Etapa | Independencia | Gran Santiago |
|---|---|---|
| Extracción de OSM y capas de contexto (`01`) | 29 s | 89 s |
| Partición en intersecciones | 0.1 s | 13.3 s |
| Agregación en calles | 0.3 s | 26.4 s |
| Construcción de las tres redes | 0.3 s | 37.8 s |
| Grafo de propiedades | 0.3 s | 32.4 s |
| Exportación de los cinco archivos | 1.2 s | 101.6 s |
| **`02` completo** | **4 s** | **217 s** |
| Pico de memoria residente en `02` | 0.4 GB | 6.7 GB |
| Pico de memoria residente en `03` | 0.3 GB | 6.4 GB |

| Salida | Independencia | Gran Santiago |
|---|---|---|
| `<área>.json` para froGQL | 4.0 MB | 438.8 MB |
| `<área>.graphml` | 6.3 MB | 686.7 MB |
| `red-auto.graphml` | 3.2 MB | 378.6 MB |
| `red-peaton.graphml` | 2.6 MB | 302.6 MB |
| `red-bici.graphml` | 2.2 MB | 243.2 MB |
| `csv/` | 1.9 MB | 215.8 MB |
| `.gdb` construido por froGQL | 2.3 MB | 233.4 MB |
| Importación del JSON | 0.2 s | 20.8 s |

Los tiempos de las doce consultas en una corrida, con froGQL 0.5.1. Cada
consulta se corre completa: el parámetro `limit` de `execute()` es un tope de
ejecución y no de presentación, así que el motor deja de producir filas al
alcanzarlo y el tiempo medido dejaría de corresponder a la consulta escrita. El
script lo deja en 0 y cada archivo `.gql` declara su propio `LIMIT`, que se
aplica después del `ORDER BY`.

| Consulta | Independencia | Gran Santiago |
|---|---|---|
| `01-lugares-en-la-misma-calle` | 1.5 ms | 0.5 ms |
| `06-lugares-a-una-cuadra` | 1.1 ms | 1.8 ms |
| `05-calles-que-cruzan` | 0.9 ms | 88 ms |
| `04-lugares-cercanos-al-ruido` | 0.8 ms | 102 ms |
| `08-ruido-por-zona-censal` | 1.7 ms | 251 ms |
| `02-ruido-por-calle` | 2.0 ms | 670 ms |
| `10-origen-de-la-asignacion` | 2.4 ms | 830 ms |
| `03-locales-de-alcohol-en-calles-con-ruido` | 4.3 ms | 903 ms |
| `11-reclamos-de-ruido-por-local` | 11.6 ms | 1.9 s |
| `12-vida-nocturna-de-foursquare` | 6.9 ms | 2.2 s |
| `09-calles-sin-lugares` | 7.4 ms | 2.8 s |
| `07-barreras-modales` | 13.2 ms | 4.2 s |

Las consultas que parten de un nodo identificado mantienen su costo al cambiar
de escala: `01` tarda medio milisegundo sobre los 460 mil nodos de la ciudad.
Las que recorren una etiqueta completa crecen con el tamaño de esa etiqueta, y
las más caras son las que recorren las tres de circulación, que son las que más
aristas tienen.

Los índices no explican esa diferencia. froGQL construye índices automáticos
sobre los pares `(etiqueta, propiedad)` de valor único al abrir la base, y en
este grafo eso cubre `Reclamo.reporte_id`, `Lugar.osm_id` y `ZonaCensal.zona_id`:
por eso la consulta `01`, que parte de un `reporte_id`, es instantánea en las dos
escalas. Declarar un BTREE sobre `Reclamo.categoria`, que es la propiedad por la
que filtran casi todas las demás, no cambia sus tiempos: el costo está en
recorrer las aristas, no en encontrar los reclamos.

Las consultas `03` y `11` preguntan lo mismo con dos formulaciones. La `03` usa
`EXISTS` para saber si la calle tiene algún reclamo por ruido; la `11` cuenta
esos reclamos con `GROUP BY`. Contar obliga a unir cada local con cada reclamo
de su calle, así que su costo crece con el producto de las dos etiquetas y no
con la suma. Con la quincena publicada la diferencia es de dos veces, 0.9
segundos contra 1.9. Sobre el año 2024 completo, que multiplica por 26 los
reclamos, la misma comparación da 3.5 segundos contra 236: el patrón de la `11`
es el que primero se degrada al crecer los datos.

## Cómo se corre

```bash
uv sync

# Comuna de Independencia
uv run python 01-preparar-datos.py
uv run python 02-caso-estudio.py
uv run python 03-consultas.py

# Gran Santiago
uv run python 01-preparar-datos.py --area santiago
uv run python 02-caso-estudio.py --area santiago
uv run python 03-consultas.py --area santiago
```

Los tres scripts están organizados en celdas `# %%` para ejecución interactiva,
y son autoejecutables. `01-preparar-datos.py` mantiene el código pesado bajo
`if __name__ == "__main__":` porque quackosm lanza sus workers con el método de
arranque "spawn", y sin ese guard cada proceso hijo reejecutaría la descarga
completa.

Los datos y las salidas de cada área viven en subdirectorios separados
(`datos/<área>/`, `salida/<área>/`), así que las dos escalas conviven sin
pisarse. Las rutas se sobreescriben con variables de entorno, que a escala de
ciudad importa porque las salidas suman varios gigabytes:

```bash
FROGQL_DATOS=/mnt/scratch/datos FROGQL_SALIDA=/mnt/scratch/salida \
    uv run python 01-preparar-datos.py --area santiago
```

Para agregar un área nueva basta agregar una entrada a `AREAS` en
`redosm/areas.py` con la lista de comunas y un rectángulo que las contenga. El
límite sale de las relaciones `boundary=administrative` con `admin_level=8` de
OSM, que es el nivel de las comunas chilenas, así que las dos escalas usan la
misma fuente y el mismo criterio.

## El modelo de grafo

Seis tipos de nodo y siete de arista.

```
(:Interseccion) -[:CONECTA_AUTO]->  (:Interseccion)
(:Interseccion) ~[:CONECTA_BICI]~   (:Interseccion)
(:Interseccion) ~[:CONECTA_PEATON]~ (:Interseccion)
(:Interseccion) -[:EN_CALLE]->      (:Calle)
(:Lugar)        -[:EN_CALLE]->      (:Calle)
(:Reclamo)      -[:EN_CALLE]->      (:Calle)
(:Venue)        -[:EN_CALLE]->      (:Calle)
(:Calle)        ~[:CRUZA_CON]~      (:Calle)
(:Reclamo)      -[:CERCA_DE]->      (:Lugar)
(:Lugar)        -[:EN_ZONA]->       (:ZonaCensal)
(:Reclamo)      -[:EN_ZONA]->       (:ZonaCensal)
(:Venue)        -[:EN_ZONA]->       (:ZonaCensal)
```

| Nodo | Independencia | Gran Santiago | Atributos principales |
|---|---|---|---|
| `Calle` | 325 | 38 427 | `nombre`, `comuna`, `tipo`, `largo_m`, `segmentos`, `permite_auto`, `permite_bici`, `permite_peaton` |
| `Interseccion` | 2610 | 288 825 | `lon`, `lat`, `grado` |
| `Lugar` | 675 | 45 613 | `etiqueta`, `nombre`, `categoria`, `amenity`, `shop`, `direccion_calle`, `lon`, `lat` |
| `Reclamo` | 226 | 21 880 | `reporte_id`, `categoria`, `grupo`, `fecha`, `hora`, `descripcion`, `lon`, `lat` |
| `Venue` | 822 | 64 382 | `venue_id`, `categoria`, `checkins`, `lon`, `lat` |
| `ZonaCensal` | 26 | 1639 | `zona_id`, `n_per`, `n_hog`, `prom_edad`, `n_transporte_*` |

| Arista | Independencia | Gran Santiago | Sentido | De | A |
|---|---|---|---|---|---|
| `EN_CALLE` | 3961 | 408 501 | dirigida | `Interseccion`, `Lugar`, `Reclamo`, `Venue` | `Calle` |
| `CERCA_DE` | 253 | 40 057 | dirigida | `Reclamo` | `Lugar` (a menos de 50 m) |
| `EN_ZONA` | 1722 | 130 320 | dirigida | `Lugar`, `Reclamo`, `Venue` | `ZonaCensal` |
| `CONECTA_AUTO` | 3527 | 420 994 | dirigida | `Interseccion` | `Interseccion` |
| `CONECTA_PEATON` | 2931 | 342 921 | no dirigida | `Interseccion` | `Interseccion` |
| `CONECTA_BICI` | 2400 | 257 392 | no dirigida | `Interseccion` | `Interseccion` |
| `CRUZA_CON` | 814 | 86 988 | no dirigida | `Calle` | `Calle` |

Los tres tipos de conexión viven sobre el mismo conjunto de intersecciones. La
partición geométrica de las ways corre una sola vez y cada modo es un
subconjunto de los mismos tramos, así que las redes se pueden comparar,
superponer y consultar juntas. Bajar una red por modo produciría tres
numeraciones de nodos distintas y esa comparación sería imposible.

## Las consultas

Los doce archivos de `consultas/` son autocontenidos: se pegan tal cual en el
REPL de froGQL o los corre `03-consultas.py`, que además mide cuánto tarda cada
uno. Están escritas en el estilo que documenta `docs/frogql-for-agents.md` del
repositorio de froGQL: `GROUP BY` después del `RETURN`, agrupación por la
variable cuando lo que importa es la identidad del nodo, y `LIMIT` como cláusula
de la consulta.

| Archivo | Qué responde |
|---|---|
| `01-lugares-en-la-misma-calle.gql` | Lugares en la misma calle que un reclamo dado |
| `02-ruido-por-calle.gql` | Calles con más reclamos por ruido |
| `03-locales-de-alcohol-en-calles-con-ruido.gql` | Locales con venta o consumo de alcohol en calles con reclamos |
| `04-lugares-cercanos-al-ruido.gql` | Lugares con más reclamos por ruido a menos de 50 m |
| `05-calles-que-cruzan.gql` | Calles que cruzan una calle dada |
| `06-lugares-a-una-cuadra.gql` | Lugares en las calles que cruzan la del reclamo |
| `07-barreras-modales.gql` | Tramos por los que circula un auto y no una bicicleta |
| `08-ruido-por-zona-censal.gql` | Reclamos por ruido y población de cada zona censal |
| `09-calles-sin-lugares.gql` | Calles con reclamos y sin ningún lugar mapeado |
| `10-origen-de-la-asignacion.gql` | Cómo se asignó cada lugar a su calle |
| `11-reclamos-de-ruido-por-local.gql` | Cuántos reclamos por ruido tiene la calle de cada local |
| `12-vida-nocturna-de-foursquare.gql` | Vida nocturna de Foursquare en calles con reclamos |

Los archivos traen el identificador `'000050'` como plantilla. Los
identificadores son correlativos por fecha dentro de cada área, así que el mismo
número apunta a reportes distintos en las dos escalas y en una de ellas puede
caer en una calle sin lugares mapeados. `03-consultas.py` busca un reclamo por
ruido que sí los tenga y lo sustituye antes de correr las consultas.

Para consultar desde el REPL:

```bash
frogql salida/santiago/frogql/santiago.gdb
gql> MATCH (a:Calle)~[:CRUZA_CON]~(b:Calle) WHERE a.nombre = 'Gamero' RETURN b.nombre
```

## Formatos de salida

Tres formatos para tres consumidores, en `salida/<área>/`:

- `graphml/red-auto.graphml`, `graphml/red-bici.graphml`,
  `graphml/red-peaton.graphml`: una red vial por modo, con la geometría de cada
  tramo codificada como WKT. GraphML es el formato XML que leen NetworkX,
  igraph, Gephi y Cytoscape.
- `graphml/<área>.graphml`: el grafo de propiedades completo. La etiqueta de
  cada nodo y de cada arista viaja en el atributo `label`, y las aristas no
  dirigidas llevan `directed="false"`.
- `frogql/<área>.json`: la vía de entrada de `frogql.import_json`. Conserva la
  direccionalidad por arista, incluidas las no dirigidas (`"~~"`).
- `frogql/csv/`: un CSV por etiqueta más `spanner_import_config.json`, para
  `frogql.import_csv`. El cargador CSV trata toda arista como dirigida, así que
  las relaciones no dirigidas se escriben en los dos sentidos y el paquete
  declara más aristas que el JSON, con los mismos nodos.

Dos restricciones del cargador CSV condicionan ese paquete y están resueltas en
`redosm/exportar.py`. La etiqueta de un nodo sale del nombre del archivo, no del
config, de ahí que los archivos se llamen `Calle.csv` o `Reclamo.csv`. Y el
cargador corta los registros por salto de línea sin reconocer los que van dentro
de un campo entrecomillado, así que el texto libre de los reclamos se normaliza
a una sola línea antes de escribirlo. El JSON no tiene esa restricción y
conserva el texto original.

Los tres formatos se escriben recorriendo los datos, sin construir el documento
completo en memoria. Para Independencia el detalle es irrelevante; para el Gran
Santiago el JSON ocupa 439 MB y el GraphML 687 MB, y el pico del pipeline llega
a siete gigabytes.

## Slides

`slides/caso-frogql/` es un deck de 30 láminas que recorre el caso: las
condiciones, el paso de OpenStreetMap a una topología, la calle como nodo, el
grafo exportado, lo que se puede preguntar y lo que los datos no tienen. Se
compila con [panduck](https://github.com/zorzalerrante/panduck) en el perfil
`slides`:

```bash
cd slides/caso-frogql && make
```

El `Makefile` corre antes `slides/figuras-slides.py`, que genera las seis
figuras propias del deck y copia los tres mapas que produce `02-caso-estudio.py`.
Los tiempos de consulta y los conteos por etiqueta los grafican desde
`salida/<área>/tiempos-consultas.csv` y `salida/<área>/resumen-grafo.csv`, que
escriben los scripts `03` y `02`, así que las cifras del deck son las de la
última corrida y no valores copiados a mano.

## Fuentes de datos

| Capa | Fuente | Descarga |
|---|---|---|
| Límites comunales | OpenStreetMap, relaciones `admin_level=8` | automática |
| Vías | OpenStreetMap, `highway=*` | automática |
| Puntos de interés | OpenStreetMap, seis tags temáticos | automática |
| Reclamos | SOSAFE, quincena anonimizada de abril de 2024 | automática, 2 MB |
| Venues | Foursquare, subconjunto de Santiago del check-in global de Yang et al. (2019) | automática, 23 MB |
| Zonas censales | Censo 2024, cartografía zonal del INE | con `--con-censo`, 758 MB |

Todo se descarga. Las capas de OpenStreetMap salen de un extracto que baja
quackosm y las de contexto, de los datasets que el curso de datos geográficos
publica en `dcc.uchile.cl/~egraells/gds-data/`. La resolución no busca en
repositorios vecinos: si dependiera de lo que hay en la máquina, el mismo
código daría resultados distintos en cada una.

Las zonas censales van aparte porque esa cartografía se publica entera, con el
país completo, y son 758 MB para quedarse con las zonas de un área. Sin ellas
el grafo se arma igual, sin nodos `ZonaCensal`, y la consulta `08` queda vacía.

Cada capa admite una variable de entorno para apuntar a una copia propia:
`FROGQL_SOSAFE`, `FROGQL_VENUES`, `FROGQL_CHECKINS` y `FROGQL_ZONAS`. Esa es la
vía para correr el caso sobre el año 2024 completo de SOSAFE, que tiene 569 204
reclamos en el Gran Santiago contra los 21 880 de la quincena, pero que no es
público.

**Los datos de OpenStreetMap son vivos.** Las cifras de este README son de una
corrida del 14 de septiembre de 2026; una corrida posterior devuelve números
algo distintos, porque el mapa cambia. Las cifras de las capas publicadas sí son
estables.

## Componentes tomados del curso de datos geográficos

El paquete `redosm/` aisla, adapta y documenta los componentes que este caso de
estudio necesita del repositorio `gds-course-materials`:

- `redosm/grafo.py` adapta `gdsutils.redes.construir_grafo_desde_lineas`. La
  partición geométrica y el armado del grafo quedan separados: la primera corre
  una vez sobre todas las ways y el segundo una vez por modo, sobre los mismos
  nodos. Se agrega el respeto del sentido de circulación, que la versión
  original no modelaba, y los tags se pegan con un join en vez de copiarse
  dentro del bucle.
- `redosm/descarga.py` adapta la extracción con quackosm de
  `profe-scripts/09-redes-santiago.py` y la función de descarga de
  `gdsutils.general`. Se agrega el recorte al polígono del área y la resolución
  del límite desde las relaciones administrativas de OSM.
- `redosm/contexto.py` toma de `gdsutils.sosafe` los grupos de categorías y la
  anonimización del texto libre.
- `redosm/calles.py` y `redosm/perfiles.py` no tienen equivalente en el curso.
  El primero define la identidad de una calle y la asignación de puntos a
  calles; el segundo, las reglas de acceso por modo de transporte.

## Decisiones de modelado y limitaciones

**La identidad de una calle combina el nombre con la conectividad.** Agrupar
solo por el tag `name` funciona en una comuna y falla en la ciudad: de los
25 873 nombres distintos del Gran Santiago, 4672 tienen tramos separados por más
de cinco kilómetros. Los Aromos son 28 ways repartidas por varias comunas, y
fundirlas en un nodo `Calle` haría que la consulta motivadora devolviera locales
de la otra punta de Santiago. Por eso los tramos se agrupan por componente
conexa dentro de cada nombre, y después se vuelven a unir los ejes homónimos
separados por menos de 150 metros, que son los cortes que deja un tramo
intermedio sin tag `name`. La distribución respalda el umbral: de los 97 151
pares de ejes homónimos, 8878 están a menos de 100 metros y la mediana de todos
los pares llega a 9.5 kilómetros. Cada nodo `Calle` lleva además
la comuna donde está la mayor parte de sus tramos, que es lo que distingue Los
Aromos de Renca de Los Aromos de Maipú en los resultados.

**El largo de una calle suma sus calzadas.** Avenida Independencia aparece con
7478 m en una comuna de tres kilómetros y medio de largo porque OSM mapea las
avenidas segregadas como dos ways paralelos y los dos llevan el mismo nombre.
Lo mismo explica los 56 726 m del eje poniente de Avenida Américo Vespucio.

**La asignación de un punto a una calle prefiere el dato declarado.** La
asignación por cercanía falla en las esquinas: un local de la avenida puede
quedar más cerca del pasaje perpendicular que del eje de la avenida. De los
lugares que declaran su calle en el tag `addr:street`, la calle más cercana es
la declarada en 73.6% de los casos en Independencia y en 63.2% en el Gran
Santiago. Por eso la asignación definitiva usa la calle declarada cuando existe
en la red y la cercanía como respaldo, y cada arista `EN_CALLE` registra en
`origen` cuál de los dos criterios se usó, para que una consulta pueda
descartar las asignaciones menos confiables. Los reclamos de SOSAFE no traen
dirección, así que su asignación es siempre por cercanía.

**Las reglas de acceso por modo son declarativas y están en un solo lugar.**
`redosm/perfiles.py` define, para cada modo, qué valores de `highway` usa por
defecto, cuáles no usa nunca y qué tags de acceso lo habilitan o lo bloquean.
Agregar un cuarto modo es agregar una entrada al diccionario `PERFILES`. Los
corredores de buses (`highway=busway`) no entran en ninguna de las tres redes
porque no admiten autos particulares, bicicletas ni peatones.

**La red ciclable y la infraestructura ciclista son cantidades distintas.** Por
13 691 km del Gran Santiago se puede pedalear legalmente y 604 km tienen
ciclovía o banda demarcada. De los 2054 ways con infraestructura declarada, 832
son ways propias (`highway=cycleway`) y 1222 la declaran como atributo de la
calzada (`cycleway:left`, `cycleway:right`): contar solo las primeras deja
fuera buena parte de la red.

**Un punto de interés entra si tiene nombre o si no es mobiliario.** Exigir
nombre propio, que era el criterio inicial, dejaba fuera comercio real: en el
Gran Santiago hay 2194 locales con tag `shop` y sin `name`, entre ellos 70
botillerías, y 179 restaurantes, bares y pubs en la misma condición. El criterio
actual descarta, cuando falta el nombre, el mobiliario urbano y el equipamiento
de parcela privada, que son las dos clases que inflan el conteo sin aportar
lugares: 6960 piscinas y 5422 canchas de casas y condominios, mapeadas desde
imágenes satelitales, más 3357 escaños y 4633 estacionamientos. Relajar el
filtro suma 8139 lugares en el Gran Santiago y 51 en Independencia. Los que
entran sin nombre conservan su categoría, y el grafo les da una `etiqueta` con
esa categoría entre paréntesis, de modo que un resultado siga siendo legible y
quede a la vista que el nombre falta en el mapa y no en el dato.

**OpenStreetMap casi no mapea bares en Chile.** Independencia tiene tres locales
con `amenity` de bar, pub o discoteca en toda la comuna, y una consulta a
Overpass sobre el mapa en vivo devuelve cuatro elementos en el mismo rectángulo:
el dato falta en OSM, no en el extracto ni en la extracción. En el Gran Santiago
son 423 para seis millones de habitantes.

Dos cosas compensan esa ausencia. La primera es que OSM sí mapea las botillerías,
que en Chile son el vector más directo del ruido en la vía pública: 19 en
Independencia y 825 en el Gran Santiago con `shop=alcohol`. Las consultas `03` y
`11` las ignoraban mientras filtraban por `amenity`; ahora filtran por
`categoria`, que combina el tag con su valor, y en Independencia el resultado
pasa de una veintena de locales a 80. La segunda es la capa de Foursquare, que
registra 26 locales nocturnos en Independencia y 3264 en el Gran Santiago, y que
la consulta `12` usa para esa categoría. El precio es que sus venues no traen
nombre y que los check-ins son de 2012, así que sitúan el fenómeno sin
identificar un local vigente.

Para una fiscalización real la pieza que falta sigue siendo el catastro
municipal de patentes de alcohol, que ninguna de las dos fuentes reemplaza.

**Los datos del grafo se anonimizan de forma parcial.** El texto libre de los
reclamos pasa por un filtro conservador que reemplaza correos y teléfonos, pero
las descripciones siguen siendo texto escrito por personas y pueden contener
referencias identificables. Los venues de Foursquare de categoría residencial
(`Home (private)`, `Residential Building`) quedan fuera del grafo, porque
publicar su ubicación expone domicilios particulares.

**La cobertura de OSM no es uniforme.** La consulta 09 lista las calles que
tienen reclamos ciudadanos y ningún lugar mapeado. La diferencia mide dónde el
mapa colaborativo está menos completo que el reporte ciudadano, no dónde no hay
actividad.
