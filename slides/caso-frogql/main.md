# Las condiciones del caso

## {.statement}

Dado un reclamo por ruido, ¿qué lugares están en la misma calle?

## Lo que hay sobre la mesa

::: columns
:::: {.column width="52%"}
Cuatro fuentes, ninguna pensada para la otra:

- **OpenStreetMap**: calles, puntos de interés y límites comunales.
- **SOSAFE**: quincena de reportes ciudadanos de abril de 2024.
- **Censo 2024**: zonas censales con población.
- **Foursquare**: venues con check-ins de 2012.
::::
:::: {.column width="48%"}
Ninguna trae el identificador de la vía. Lo único que comparten es estar en el mismo lugar del mapa.

Las cuatro se descargan solas, así que el caso se reproduce desde un clon del repositorio.
::::
:::

## Responder con geometría cuesta en cada consulta

::: columns
:::: {.column width="50%"}
Con capas geográficas, "la misma calle" es un buffer y un umbral de distancia que hay que recalcular cada vez.

Con la calle como **nodo** del grafo, es un patrón de dos aristas.
::::
:::: {.column width="50%"}
```{.dot width="100%"}
digraph Q {
  bgcolor="transparent"; rankdir=LR;
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=11];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=10];
  r [label="Reclamo", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  c [label="Calle", fillcolor="#0A0E50", fontcolor="white"];
  l [label="Lugar", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  r -> c [label=" EN_CALLE"];
  l -> c [label=" EN_CALLE"];
}
```
::::
:::

# De OpenStreetMap a una topología

## Una way de OSM no es una arista {.smaller}

::: columns
:::: {.column width="46%"}
Una way puede atravesar diez esquinas sin declarar ninguna, y dos calles que se cruzan comparten la coordenada sin compartir un identificador.

Antes de tener grafo hay que agrupar las coordenadas que coinciden y cortar cada way en los nodos que comparte.
::::
:::: {.column width="54%"}
```{.dot width="100%"}
digraph T {
  bgcolor="transparent"; rankdir=LR;
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=10];
  edge [fontname="Urbanist", color="#0A0E50"];
  a [label="Ways con tag\nhighway"];
  b [label="Agrupar coordenadas\na 1.5 m (KDTree)"];
  c [label="Cortar en los nodos\ncompartidos"];
  d [label="Intersecciones\ny segmentos", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  a -> b -> c -> d;
}
```
::::
:::

En Independencia, 1683 ways producen **2610 intersecciones** y **3551 segmentos**. En el Gran Santiago, 183 797 ways producen 288 825 y 413 831.

## Un solo conjunto de nodos, tres redes {.smaller}

::: columns
:::: {.column width="50%"}
La partición corre **una vez** sobre todas las ways. Cada modo es después un subconjunto de los mismos segmentos.

Bajar una red por modo daría tres numeraciones de nodos distintas, y las redes no se podrían comparar ni superponer.
::::
:::: {.column width="50%"}
Las reglas de acceso son declarativas: por cada modo, qué valores de `highway` usa, cuáles no usa nunca y qué tags lo bloquean.

La red de autos es dirigida y respeta `oneway`; las otras dos no.
::::
:::

## {.image}

![Las tres redes de Independencia sobre las mismas intersecciones. Los 143 km para auto, 138 para bicicleta y 147 a pie son el mismo material filtrado por tres reglas distintas.](img/redes-por-modo.png){width="92%"}

## {.image}

![Por casi toda la comuna se puede pedalear legalmente y solo 11.8 km tienen ciclovía o banda demarcada. De los 54 ways con infraestructura declarada, 44 la declaran como atributo de la calzada y no como way propia.](img/infraestructura-ciclista.png){width="46%"}

# La calle como nodo

## Tres criterios para decir que dos tramos son la misma calle {.smaller}

::: columns
:::: {.column width="52%"}
1. **El nombre.** El tag `name` de OSM.
2. **La conectividad.** Dos tramos con el mismo nombre son el mismo eje solo si hay camino entre ellos.
3. **La reunión.** Cuando a un tramo intermedio le falta el tag, el eje se parte en dos pedazos que quedan a pocos metros.
::::
:::: {.column width="48%"}
El segundo criterio hace falta en la ciudad: de los 25 873 nombres del Gran Santiago, **4672 tienen tramos separados por más de cinco kilómetros**.

Los Aromos son 28 ways repartidas por varias comunas.
::::
:::

## {.image}

![El tercer criterio necesita un umbral. El pico bajo los 100 metros son cortes accidentales y la cola son calles distintas que comparten nombre, así que 150 metros cubre el pico sin fundir comunas.](img/ejes-homonimos.png){width="82%"}

## Cómo se cuelga un punto de su calle {.smaller}

::: columns
:::: {.column width="50%"}
La asignación por cercanía falla en las esquinas: un local de la avenida puede quedar más cerca del pasaje perpendicular que del eje de la avenida.

Parte de los puntos de interés declara su calle en el tag `addr:street`. Cuando esa calle existe en la red, se usa esa.
::::
:::: {.column width="50%"}
La coincidencia entre el eje más cercano y el declarado es de **74%** en Independencia y **63%** en el Gran Santiago.

Cada arista `EN_CALLE` guarda en `origen` cuál de los dos criterios se usó, así una consulta puede descartar lo menos confiable.
::::
:::

## {.image}

![Con el dato declarado la mayoría de los lugares no depende de la cercanía. Los que quedan sin calle están a más de 40 metros de cualquier eje con nombre.](img/asignacion-lugares.png){width="88%"}

# El grafo exportado

## Seis tipos de nodo, siete de arista

```{.dot width="66%"}
digraph M {
  bgcolor="transparent"; rankdir=LR; nodesep=0.16; ranksep=0.62;
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.4, fontsize=10, height=0.32];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=8];
  i [label="Interseccion", fillcolor="#0A0E50", fontcolor="white"];
  c [label="Calle", fillcolor="#0A0E50", fontcolor="white"];
  r [label="Reclamo", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  l [label="Lugar"];
  v [label="Venue"];
  z [label="ZonaCensal"];
  i -> i [label=" CONECTA_AUTO, _BICI, _PEATON"];
  c -> c [label=" CRUZA_CON"];
  i -> c [label=" EN_CALLE"];
  l -> c; r -> c; v -> c;
  r -> l [label=" CERCA_DE"];
  l -> z [label=" EN_ZONA"];
  r -> z; v -> z;
}
```

Las cuatro aristas sin rótulo hacia `Calle` son `EN_CALLE`, y las dos sin rótulo hacia `ZonaCensal` son `EN_ZONA`.

## {.image}

![El mismo modelo a dos escalas: 4684 nodos y 15 608 aristas en la comuna, 460 766 y 1 687 173 en la ciudad. Las intersecciones dominan los nodos y la circulación domina las aristas.](img/escala.png){width="92%"}

## Tres formatos, tres consumidores {.smaller}

::: columns
:::: {.column width="34%"}
**GraphML**

Una red por modo más el grafo completo. Lo leen NetworkX, igraph, Gephi.
::::
:::: {.column width="33%"}
**JSON**

La vía de entrada de froGQL. Conserva la direccionalidad de cada arista.
::::
:::: {.column width="33%"}
**CSV**

Un archivo por etiqueta. Su cargador trata toda arista como dirigida.
::::
:::

Los tres se escriben recorriendo los datos y no construyendo el documento en memoria: el JSON de la ciudad pesa 439 MB y froGQL lo carga en 21 segundos.

# Lo que se puede preguntar

## La consulta que motiva el modelo {.smaller}

```
MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle)<-[:EN_CALLE]-(l:Lugar)
WHERE r.reporte_id = '000000'
RETURN c.nombre AS calle, l.etiqueta AS lugar
```

El reclamo dice "Música alta, 20.00, por favor, no se puede estar tranquilo" y está en Avenida Independencia. La consulta devuelve los locales de esa calle, entre ellos siete tiendas de telas y una comisaría, en un milisegundo.

## {.image}

![Los reclamos por ruido de 2024 agregados por calle. La unidad del grafo coincide con la unidad de la operación municipal, que recorre ejes y no puntos.](img/ruido-por-calle.png){width="52%"}

## {.image}

![Las consultas que parten de un nodo identificado no cambian de costo entre las dos escalas. Las que recorren una etiqueta completa crecen con ella.](img/tiempos-consultas.png){width="90%"}

## El costo depende de cómo se escriba la pregunta {.smaller}

::: columns
:::: {.column width="50%"}
Dos consultas preguntan por locales de alcohol en calles con reclamos por ruido.

Una usa `EXISTS` para saber si la calle tiene alguno. La otra los cuenta con `GROUP BY`.
::::
:::: {.column width="50%"}
Contar obliga a unir cada local con cada reclamo de su calle. En Avenida Irarrázaval hay 393 lugares y 66 reclamos por ruido, y ese producto se paga entero antes de agrupar.

En la ciudad: **0.9 segundos contra 1.9**. Con el año 2024 completo, que multiplica por 26 los reclamos, la misma comparación da **3.5 contra 236**.
::::
:::

# Lo que los datos no tienen

## {.image}

![OpenStreetMap casi no mapea bares en Chile y Overpass confirma que el dato falta en el mapa, no en el extracto. Lo que OSM sí tiene son las botillerías, que es el vector más directo del ruido en la vía pública.](img/cobertura-nocturna.png){width="84%"}

## {.image}

![La adopción de SOSAFE sigue el nivel socioeconómico de la comuna. Comparar comunas con los conteos crudos financiaría a las que más reportan.](img/sesgo-sosafe.png){width="42%"}

# Síntesis

## {.statement}

Reificar la calle como nodo convierte una consulta geométrica en dos aristas, y el costo no cambia al pasar de una comuna a la ciudad.

Lo que sí cambia con la escala son los criterios: la identidad de una calle y la comparabilidad de los reportes ciudadanos.

## ¡Gracias! {.end}

egraells@dcc.uchile.cl
