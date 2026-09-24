## {.statement}

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
Con una planilla hay que medir la distancia de cada punto del mapa a cada calle y decidir a mano cuánto es "cerca". De nuevo para cada pregunta.

Preguntar cuesta tanto que la pregunta se deja de hacer.
::::
:::

## froGQL guarda la relación en lugar de recalcularla

::: columns
:::: {.column width="46%"}
La calle pasa a ser una cosa en la base de datos, con reclamos y locales colgando de ella.

"Qué hay en esta calle" se responde siguiendo dos flechas. Sin medir distancias y sin decidir qué es cerca.

La respuesta ya está guardada en la forma de los datos.
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
:::: {.column width="52%"}
![](img/qr.png){width="40%"}

Escaneen y consulten su propia calle. Funciona aunque apaguen los datos.
::::
:::: {.column width="48%"}
![](img/pantalla.png){width="46%"}
::::
:::

## Lo que acaba de correr en su teléfono

::: columns
:::: {.column width="50%"}
| El demo en números | |
|---|---|
| Esquinas, calles y locales | 4658 |
| Relaciones entre ellos | 13 886 |
| La base más el motor | 768 KB |
| En abrirla | 70 ms |
| En responder | 3 ms |
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

La misma consulta sobre el Gran Santiago entero, cien veces más grande, tarda lo mismo que sobre esta comuna: medio milisegundo.
::::
:::

## Preguntar por caminos es donde SQL se complica

::: columns
:::: {.column width="52%"}
La misma historia, una pregunta más allá:

> ¿Qué botillerías y bares hay a una o dos cuadras del reclamo?

froGQL responde en **42 milisegundos** con 20 locales. El primero es la Botillería Víctor, en Lastra, a una cuadra.
::::
:::: {.column width="48%"}
Todo el peso lo lleva el pedazo que dice "una o dos cuadras":

`{1,2}`

En SQL hay que escribir una consulta que se llama a sí misma, juntar los resultados de cada nivel y decidir a mano dónde parar.

Cambiar dos cuadras por cinco: acá es cambiar un número.
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

Habla GQL, el lenguaje de consulta de grafos que ISO aprobó en 2024. Es el primer estándar nuevo de este tipo desde SQL.

La base es un archivo. No hay servidor que instalar ni que administrar.
::::
:::: {.column width="50%"}
**Dónde corre.** Desde Python, desde JavaScript, desde la línea de comandos y dentro del navegador, compilada a WebAssembly, que es lo que le permite correr en el teléfono de cada uno de ustedes.

**Qué no es.** Un reemplazo para las bases gigantes repartidas en muchos servidores. Sirve cuando los datos caben en el aparato de quien pregunta, que es casi siempre.
::::
:::

## Pruébenla {.end}

Todo el caso es reproducible: los datos se descargan solos.

`pip install frogql` · github.com/pleiad/frogql
