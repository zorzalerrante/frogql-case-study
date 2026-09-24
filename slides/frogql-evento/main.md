# {.statement}

Una base de datos que cabe en menos de un megabyte, viaja dentro de la página web y responde en milisegundos preguntas que a una planilla le toman medio mapa.

Está hecha en Chile y pueden probarla desde sus teléfonos en los próximos diez minutos.

## Hay preguntas que nadie hace porque responderlas cuesta caro

::: columns
:::: {.column width="52%"}
Un vecino de Independencia reportó esto en abril de 2024:

> Música alta...20.00...porfavor...no se puede estar tranquilo

La pregunta que sigue es obvia para cualquiera que viva ahí: **qué hay en esa calle**. Un bar, una botillería, un local de comida.
::::
:::: {.column width="48%"}
Con planillas y capas geográficas, responderla exige comparar cada punto del mapa con cada calle y fijar un umbral de distancia. Cada vez, para cada pregunta nueva.

El costo de preguntar es tan alto que la pregunta se deja de hacer.
::::
:::

## froGQL guarda la relación en lugar de recalcularla

::: columns
:::: {.column width="46%"}
La calle pasa a ser una cosa en la base de datos, con reclamos y locales colgando de ella.

"Qué hay en esta calle" se responde siguiendo dos flechas. Sin geometría, sin umbrales, sin recalcular.

Y quien pregunta escribe la pregunta que quiera.
::::
:::: {.column width="54%"}
```{.dot width="100%"}
digraph Q {
  bgcolor="transparent"; rankdir=LR;
  node [fontname="Urbanist", shape=box, style="rounded,filled", fillcolor="white", color="#0A0E50", fontcolor="#0A0E50", penwidth=1.5, fontsize=12];
  edge [fontname="Urbanist", color="#0A0E50", fontcolor="#0A0E50", fontsize=11];
  r [label="El reclamo", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  c [label="La calle", fillcolor="#0A0E50", fontcolor="white"];
  l [label="El local", fillcolor="#CF3889", fontcolor="white", color="#CF3889"];
  r -> c [label=" está en"];
  l -> c [label=" está en"];
}
```
::::
:::

## Demostración: la comuna entera, en su teléfono, en modo avión

::: columns
:::: {.column width="38%"}
![](img/qr.png){width="72%"}

Escaneen y consulten su propia calle. Funciona aunque apaguen los datos.
::::
:::: {.column width="62%"}
![](img/pantalla.png){width="52%"}
::::
:::

## Lo que acaba de correr en su teléfono

::: columns
:::: {.column width="50%"}
| | |
|---|---|
| Barrios y esquinas | 4658 |
| Relaciones entre ellos | 13 886 |
| La base completa | 342 KB |
| El motor de consultas | 426 KB |
| En abrirla | 70 ms |
| En responder | 3 ms |
| Servidores involucrados | ninguno |
::::
:::: {.column width="50%"}
La base entera pesa menos que una foto del teléfono, y responde en menos tiempo del que dura un parpadeo.

Nada de esto viajó a un servidor. Bajó una vez y quedó en el aparato.
::::
:::

## La pregunta la escribe quien consulta

::: columns
:::: {.column width="50%"}
No hay un menú fijo de consultas. La sala puede pedir una pregunta distinta y la escribimos en vivo, sin rehacer la base y sin volver a publicar nada.

Esa es la diferencia con un tablero o un informe: el tablero responde lo que alguien previó, la base responde lo que a usted se le ocurra.
::::
:::: {.column width="50%"}
Y el tamaño no cambia el costo cuando la pregunta parte de un punto conocido.

La misma consulta sobre el Gran Santiago, con **460 mil** nodos y **1,7 millones** de relaciones, tarda lo mismo que sobre esta comuna: medio milisegundo.
::::
:::

## Donde no hay conexión, o donde no debe haberla

::: columns
:::: {.column width="50%"}
- Catastro y terreno sin señal
- Rondas de salud rural
- Material educativo en salas sin wifi
- Guías de museo y de feria
::::
:::: {.column width="50%"}
- Datos sensibles que no deben salir del dispositivo
- Periodismo con la base en el computador
- Cualquier aplicación que hoy depende de que el servidor conteste
::::
:::

La base viaja dentro de la aplicación, así que la aplicación sigue respondiendo cuando la red falla.

## froGQL en una lámina {.smaller}

::: columns
:::: {.column width="50%"}
**Qué es.** Un motor de bases de datos de grafos hecho en Chile, en el laboratorio Pleiad del Departamento de Ciencias de la Computación de la Universidad de Chile.

Implementa GQL, el estándar ISO de consulta de grafos aprobado en 2024, el primero desde SQL.

Es embebida: la base es un archivo y no hay servidor que instalar ni administrar.
::::
:::: {.column width="50%"}
**Dónde corre.** Desde Python, desde Node, desde la línea de comandos y dentro del navegador compilada a WebAssembly.

**Qué no es.** Un reemplazo de un motor distribuido sobre terabytes. Brilla cuando la base cabe en el aparato de quien pregunta, que es la mayoría de los casos que no son una empresa grande.
::::
:::

## El caso que vieron está completo y abierto

::: columns
:::: {.column width="52%"}
La comuna de Independencia como grafo: calles, esquinas, locales, reclamos ciudadanos y zonas censales, construido desde OpenStreetMap y datos públicos.

Todo se descarga solo, así que cualquiera reproduce el caso desde un clon del repositorio.
::::
:::: {.column width="48%"}
![](img/ruido-por-calle.png){width="88%"}
::::
:::

## Pruébenla {.end}

`pip install frogql` · `npm install frogql-wasm`

github.com/pleiad/frogql
