## froGQL guarda la comuna como un grafo que cabe en el teléfono

::: columns
:::: {.column width="58%"}
```{.dot width="100%"}
digraph G {
  bgcolor="transparent";
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=20, margin="0.18,0.08"];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=16];
  rankdir=LR; nodesep=0.35; ranksep=0.8;
  r [label="Reclamo\n\"Música alta...\"", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  p [label="Club Papa Rock"];
  b [label="Barracuda"];
  a [label="Avenida\nIndependencia", fillcolor="#0A0E50", fontcolor="white"];
  g [label="Gamero", fillcolor="#0A0E50", fontcolor="white"];
  r -> a [label="EN_CALLE"];
  p -> a; b -> a;
  a -> g [label="CRUZA_CON", dir=none];
}
```

Un trozo del grafo de la comuna de Independencia.
::::
:::: {.column width="42%"}
- La base de Independencia y el motor pesan 768 KB y se descargan con la página web.
- Las consultas corren en el teléfono y responden en milisegundos, sin conexión.
- La desarrolla el DCC de la Universidad de Chile.
::::
:::

## Un reclamo por ruido lleva a preguntar qué hay en su calle

::: columns
:::: {.column width="54%"}
> Música alta...20.00...porfavor...no se puede estar tranquilo

Para responder hay que cruzar el reclamo de SOSAFE con los locales de OpenStreetMap.
::::
:::: {.column width="46%"}
![](img/pregunta.png){height="9.2cm"}
::::
:::

## El grafo guarda la calle de cada local

::: columns
:::: {.column width="50%"}
Una planilla mide la distancia de cada local a cada calle.

```{.dot width="90%"}
digraph P {
  bgcolor="transparent";
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=20, margin="0.18,0.08"];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=16];
  rankdir=LR; ranksep=1.6; nodesep=0.3;
  v [label="Botilleria Victor"]; w [label="Botillería Victoria"];
  p [label="Club Papa Rock"]; b [label="Barracuda"];
  l [label="Lastra", fillcolor="#0A0E50", fontcolor="white"]; r [label="Rivera", fillcolor="#0A0E50", fontcolor="white"];
  a [label="Av. Independencia", fillcolor="#0A0E50", fontcolor="white"];
  {rank=same; v -> w -> p -> b [style=invis];}
  {rank=same; l -> r -> a [style=invis];}
  edge [style=dashed, color="#a9a9bd", arrowhead=none];
  {v w p b} -> {l r a};
}
```
::::
:::: {.column width="50%"}
El grafo guarda una arista `EN_CALLE` por local.

```{.dot width="90%"}
digraph G2 {
  bgcolor="transparent";
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=20, margin="0.18,0.08"];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=16];
  rankdir=LR; ranksep=1.6; nodesep=0.3;
  v [label="Botilleria Victor"]; w [label="Botillería Victoria"];
  p [label="Club Papa Rock"]; b [label="Barracuda"];
  l [label="Lastra", fillcolor="#0A0E50", fontcolor="white"]; r [label="Rivera", fillcolor="#0A0E50", fontcolor="white"];
  a [label="Av. Independencia", fillcolor="#0A0E50", fontcolor="white"];
  {rank=same; v -> w -> p -> b [style=invis];}
  {rank=same; l -> r -> a [style=invis];}
  v -> l; w -> r; p -> a; b -> a;
}
```
::::
:::

Con los 675 lugares y las 325 calles de Independencia, la planilla mide 219 375 distancias en cada pregunta. El grafo guarda 631 aristas, una por cada lugar con calle asignada.

## En la calle del reclamo hay 132 lugares, entre ellos una discoteca y dos botillerías

::: columns
:::: {.column width="50%"}
![](img/respuesta.png){height="9.2cm"}
::::
:::: {.column width="50%"}
```{.dot width="80%"}
digraph Q {
  bgcolor="transparent";
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=20, margin="0.18,0.08"];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=16];
  rankdir=LR;
  r [label="El reclamo", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  c [label="La calle", fillcolor="#0A0E50", fontcolor="white"];
  l [label="El local"];
  r -> c [label=" está en"];
  l -> c [label=" está en"];
}
```

La base guarda a qué calle pertenece cada lugar, así que la consulta recorre dos aristas.

froGQL encontró los 132 lugares en 3 milisegundos.
::::
:::

## La página descarga la base y el motor una vez

::: columns
:::: {.column width="56%"}
![](img/qr.png){height="3.6cm"}

```{.dot width="100%"}
digraph T {
  bgcolor="transparent";
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=20, margin="0.18,0.08"];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=16];
  rankdir=LR; nodesep=0.3; ranksep=0.5;
  web [label="Página web"];
  subgraph cluster_telefono {
    label="Teléfono"; labelloc=b; fontname="Urbanist"; fontcolor="#0A0E50"; fontsize=18;
    style=rounded; color="#0A0E50"; penwidth=1.2;
    q [label="Consulta", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
    m [label="froGQL\ny el grafo", fillcolor="#0A0E50", fontcolor="white"];
    s [label="Resultado"];
    q -> m -> s;
  }
  web -> m [label="768 KB,\nuna vez"];
}
```

Sin red, el mapa de fondo no carga, pero las consultas siguen respondiendo.
::::
:::: {.column width="44%"}
![](img/movil-01.png){height="9.6cm"}
::::
:::

## El grafo de Independencia tiene 4658 nodos y 13 886 aristas

::: columns
:::: {.column width="58%"}
```{.dot width="100%"}
digraph E {
  bgcolor="transparent";
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=20, margin="0.18,0.08"];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=16];
  rankdir=TB; nodesep=0.35; ranksep=1.1;
  r [label="Reclamo\n226", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  l [label="Lugar\n675"];
  v [label="Venue\n822"];
  i [label="Intersección\n2610", fillcolor="#e4e4ee", color="#a9a9bd"];
  c [label="Calle\n325", fillcolor="#0A0E50", fontcolor="white"];
  {rank=same; r; l; v; i;}
  r -> l [label="CERCA_DE 253", constraint=false];
  r -> c [label="204"]; l -> c [label="631"]; v -> c [label="608"]; i -> c [label="2518"];
  c -> c [label=" CRUZA_CON\n 814"];
  i -> i [label=" CONECTA\n 8858"];
}
```

Las flechas hacia `Calle` son aristas `EN_CALLE`. `CONECTA` suma las redes de auto, bici y peatón.
::::
:::: {.column width="42%"}
- Los datos son de OpenStreetMap, SOSAFE (abril de 2024) y Foursquare.
- La base y el motor pesan 768 KB comprimidos.
- Abrir la base toma 100 ms y la consulta del reclamo, 3 ms.
- En el Gran Santiago, con cien veces más nodos, esa consulta tarda lo mismo.
::::
:::

## Cada constante de la consulta es un parámetro

::: columns
:::: {.column width="48%"}
- La categoría del reclamo, la calle y el tipo de local se eligen en pantalla.
- Un reclamo o una calle también se eligen tocándolos en el mapa.
- Cada cambio vuelve a correr la consulta.

En la versión de una columna, la consulta también se edita y se corre en vivo, sin rehacer la base.
::::
:::: {.column width="52%"}
![](img/parametros-03.png){height="8.6cm"}
::::
:::

## {.image}

![La consulta de locales con alcohol en calles con reclamos por ruido, sin los restaurantes. Las calles y los locales del resultado quedan encendidos sobre la red de la comuna.](img/escritorio-03.png){width="96%"}

## Un patrón de largo variable recorre una o dos cuadras

> Con tanto ruido me dio sed... ¿qué botillerías y bares hay a una o dos cuadras?

::: columns
:::: {.column width="55%"}
```
MATCH (mi:Calle)
  ~[:CRUZA_CON]~{1,2}
  (otra:Calle)<-[:EN_CALLE]-(l:Lugar)
WHERE mi.nombre =
      'Avenida Independencia'
  AND l.categoria IN
      ['amenity=bar', 'shop=alcohol']
RETURN DISTINCT l.etiqueta AS local,
       otra.nombre AS calle
```
::::
:::: {.column width="45%"}
```{.dot width="92%"}
digraph C {
  bgcolor="transparent";
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=20, margin="0.18,0.08"];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=16];
  rankdir=TB; nodesep=0.3; ranksep=0.45;
  a [label="Avenida Independencia", fillcolor="#0A0E50", fontcolor="white"];
  g [label="Gamero", fillcolor="#0A0E50", fontcolor="white"];
  p [label="El Pino", fillcolor="#0A0E50", fontcolor="white"];
  e [label="Botillería\nLas Enredaderas", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  a -> g [label=" cruza con", dir=none];
  g -> p [label=" cruza con", dir=none];
  e -> p [label=" EN_CALLE"];
  {rank=same; p; e;}
}
```

En SQL, este recorrido requiere una consulta recursiva.
::::
:::

## {.image}

![froGQL encontró 18 locales en 33 milisegundos. Las calles a una y dos cuadras de la Avenida Independencia cubren casi toda la comuna.](img/caminos.png){height="11cm"}

## froGQL sirve cuando los datos caben en el dispositivo de quien consulta

::: {.definition title="Qué es"}
Un motor de bases de datos de grafos desarrollado en el DCC de la Universidad de Chile. Usa GQL, el lenguaje que ISO estandarizó en 2024, y corre en Python, en JavaScript y en el navegador, sin servidor.
:::

- Trabajo en terreno sin señal, como un catastro o una ronda de salud rural.
- Material educativo y guías de museo en lugares sin wifi.
- Datos sensibles que se consultan sin enviarlos a un servidor.

La base viaja dentro de la aplicación, que responde aunque falle la red.

## El código QR abre la demo {.end image="img/qr.png"}

Los scripts del repositorio descargan los datos, así que el caso se reproduce desde un clon.

`pip install frogql` · github.com/pleiad/frogql
