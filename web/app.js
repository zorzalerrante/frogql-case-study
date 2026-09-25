// Carga el grafo de Independencia en froGQL compilado a WebAssembly y corre
// los .gql del repositorio.
//
// El motor es un backend en RAM: no hay sistema de archivos en el navegador,
// así que la entrada es el JSON que exporta `redosm/exportar.py` y no el
// `.gdb`. La versión del motor la fija `preparar-web.py`.
import init, { open_json } from "./vendor/frogql_wasm.js";
import { crearMapa } from "./mapa.js";
import { constantesDe, etiquetasDe } from "./grafo.js";

// El identificador que traen los .gql como plantilla. Los identificadores son
// correlativos por área, así que hay que reemplazarlo por uno que exista acá.
const PLANTILLA = "000050";
// Sin tope de filas. Igual que en `03-consultas.py`: cada .gql declara su
// propio LIMIT, que se aplica después del ORDER BY.
const SIN_TOPE = 0;
// Celdas más largas que esto se dejan partir en varias líneas.
const LARGO_TEXTO = 60;
// Filas que se dibujan. No acota la consulta, que corre completa: es el mismo
// criterio de `03-consultas.py`, donde el tope de presentación y el de
// ejecución son cosas distintas.
const FILAS_VISIBLES = 25;
// Columnas cuyo valor no es un nombre de calle aunque coincida con uno. La
// comuna es el caso claro: "Independencia" es comuna y también calle.
const COLUMNAS_NO_UBICABLES = new Set(["comuna", "categoria", "tipo", "origen", "modo"]);
// Las coordenadas son identificadores y no cantidades: separarlas por miles y
// redondearlas a tres decimales las vuelve otra cosa.
const SIN_FORMATO = new Set(["lon", "lat"]);
// Largo del relato de un reclamo en la tarjeta del mapa. Los de SOSAFE llegan a
// varios renglones y taparían el mapa.
const LARGO_RELATO = 130;

const $ = (id) => document.getElementById(id);

const numero = new Intl.NumberFormat("es-CL");
const ms = (valor) => (valor < 10 ? valor.toFixed(1) : Math.round(valor)) + " ms";
/** "1 calle" y "20 calles", que la pantalla se lee en voz alta. */
const contar = (cantidad, singular, plural) =>
  `${numero.format(cantidad)} ${cantidad === 1 ? singular : plural}`;

/** Dibuja la consulta con sus constantes como botones. */
function codigoConConstantes(gql, alPulsar) {
  const pre = document.createElement("pre");
  pre.className = "codigo";
  let cursor = 0;
  for (const constante of constantesDe(gql)) {
    if (constante.inicio < cursor) continue;
    pre.append(document.createTextNode(gql.slice(cursor, constante.inicio)));
    const boton = document.createElement("button");
    boton.className = "constante";
    boton.type = "button";
    boton.textContent = `'${constante.valor}'`;
    boton.title = `Ver el ${constante.etiqueta} con ${constante.propiedad} = ${constante.valor}`;
    boton.addEventListener("click", () => alPulsar(constante));
    pre.append(boton);
    cursor = constante.fin;
  }
  pre.append(document.createTextNode(gql.slice(cursor)));
  return pre;
}

function tabla(filas) {
  const visibles = filas.slice(0, FILAS_VISIBLES);
  const columnas = [...new Set(visibles.flatMap((fila) => Object.keys(fila)))];
  const tabla = document.createElement("table");

  const encabezado = tabla.createTHead().insertRow();
  for (const columna of columnas) {
    const celda = document.createElement("th");
    celda.textContent = columna;
    encabezado.append(celda);
  }

  const cuerpo = tabla.createTBody();
  for (const fila of visibles) {
    const tr = cuerpo.insertRow();
    for (const columna of columnas) {
      const valor = fila[columna];
      const celda = tr.insertCell();
      celda.textContent =
        valor === null || valor === undefined
          ? "—"
          : typeof valor === "number"
            ? numero.format(valor)
            : String(valor);
      if (celda.textContent.length > LARGO_TEXTO) celda.classList.add("largo");
    }
  }
  return tabla;
}

function ficha(consulta, correr, alTerminar, inspeccionar) {
  const seccion = document.createElement("section");
  seccion.className = "consulta";

  const encabezado = document.createElement("div");
  encabezado.className = "encabezado";
  const numeroConsulta = document.createElement("span");
  numeroConsulta.className = "numero";
  numeroConsulta.textContent = consulta.numero;
  const titulo = document.createElement("h2");
  titulo.textContent = consulta.titulo;
  encabezado.append(numeroConsulta, titulo);

  const explicacion = document.createElement("p");
  explicacion.className = "explicacion";
  explicacion.textContent = consulta.explicacion;

  const detalle = document.createElement("details");
  const resumen = document.createElement("summary");
  resumen.textContent = `${consulta.archivo} · ver, editar y explorar`;

  const inspector = document.createElement("div");
  inspector.className = "inspector";
  inspector.hidden = true;

  const codigo = codigoConConstantes(consulta.gql, (constante) =>
    inspeccionar(constante, inspector),
  );

  const editor = document.createElement("textarea");
  editor.className = "editor";
  editor.spellcheck = false;
  editor.hidden = true;
  editor.value = consulta.gql;
  // El textarea crece con el texto: en el teléfono no se puede desplazar dentro
  // de una caja que ya está dentro de otra.
  const ajustar = () => {
    editor.style.height = "auto";
    editor.style.height = editor.scrollHeight + "px";
  };
  editor.addEventListener("input", ajustar);

  const edicion = document.createElement("div");
  edicion.className = "edicion";
  const editarBoton = document.createElement("button");
  editarBoton.className = "enlace";
  editarBoton.type = "button";
  editarBoton.textContent = "Editar";
  const restaurarBoton = document.createElement("button");
  restaurarBoton.className = "enlace";
  restaurarBoton.type = "button";
  restaurarBoton.textContent = "Volver al original";
  restaurarBoton.hidden = true;
  const nota = document.createElement("span");
  nota.className = "nota";
  edicion.append(editarBoton, restaurarBoton, nota);

  let editando = false;
  const modoEdicion = (activo) => {
    editando = activo;
    codigo.hidden = activo;
    editor.hidden = !activo;
    editarBoton.hidden = activo;
    restaurarBoton.hidden = !activo;
    inspector.hidden = true;
    nota.textContent = activo
      ? "Al editar se pierde el vínculo de las constantes con el grafo."
      : "";
    if (activo) {
      ajustar();
      editor.focus();
    }
  };
  editarBoton.addEventListener("click", () => modoEdicion(true));
  restaurarBoton.addEventListener("click", () => {
    editor.value = consulta.gql;
    modoEdicion(false);
  });

  detalle.append(resumen, codigo, editor, edicion, inspector);
  const textoActual = () => (editando ? editor.value : consulta.gql);

  const acciones = document.createElement("div");
  acciones.className = "acciones";
  const boton = document.createElement("button");
  boton.textContent = "Correr";
  const tiempo = document.createElement("span");
  tiempo.className = "tiempo";
  acciones.append(boton, tiempo);

  const salida = document.createElement("div");

  seccion.append(encabezado, explicacion, detalle, acciones, salida);

  if (consulta.faltan.length) {
    seccion.classList.add("vacia");
    boton.disabled = true;
    const nota = document.createElement("p");
    nota.className = "sin-filas";
    nota.textContent =
      `El grafo cargado no tiene ${consulta.faltan.join(" ni ")}, así que esta ` +
      "consulta no devuelve filas. Se agregan corriendo 01-preparar-datos.py --con-censo.";
    salida.append(nota);
    return { seccion, correr: null };
  }

  const ejecutar = () => {
    boton.disabled = true;
    boton.textContent = "Corriendo…";
    salida.replaceChildren();
    // Un cuadro de animación antes de bloquear el hilo, para que el botón
    // alcance a repintarse: el motor corre en el hilo de la interfaz.
    return new Promise((listo) =>
      requestAnimationFrame(() => {
        const resultado = correr(textoActual());
        boton.disabled = false;
        boton.textContent = "Correr de nuevo";
        tiempo.textContent = resultado.error ? "" : ms(resultado.milisegundos);
        if (resultado.error) {
          const error = document.createElement("pre");
          error.textContent = resultado.error;
          salida.append(error);
        } else if (!resultado.filas.length) {
          const nota = document.createElement("p");
          nota.className = "sin-filas";
          nota.textContent = "Sin filas.";
          salida.append(nota);
        } else {
          const marco = document.createElement("div");
          marco.className = "tabla";
          marco.append(tabla(resultado.filas));
          salida.append(marco);
          const pie = document.createElement("p");
          pie.className = "sin-filas";
          const total = resultado.filas.length;
          pie.textContent =
            total > FILAS_VISIBLES
              ? `${FILAS_VISIBLES} de ${numero.format(total)} filas.`
              : contar(total, "fila.", "filas.");
          salida.append(pie);
        }
        alTerminar?.(consulta, resultado);
        listo(resultado);
      }),
    );
  };

  boton.addEventListener("click", ejecutar);
  return { seccion, correr: ejecutar };
}

async function arrancar() {
  const cifras = $("cifras");
  const pintarCifras = (items) => {
    cifras.replaceChildren(
      ...items.map(([etiqueta, valor]) => {
        const li = document.createElement("li");
        li.append(document.createTextNode(etiqueta + " "));
        const b = document.createElement("b");
        b.textContent = valor;
        li.append(b);
        return li;
      }),
    );
  };

  const marca = performance.now();
  await init();
  const motor = performance.now() - marca;

  const [grafo, consultas] = await Promise.all([
    fetch("./datos/independencia.json").then((r) => r.text()),
    fetch("./datos/consultas.json").then((r) => r.json()),
  ]);

  const inicioCarga = performance.now();
  const conexion = open_json(grafo);
  const carga = performance.now() - inicioCarga;

  const esquema = conexion.schema();
  const presentes = new Set([...esquema.node_labels, ...esquema.edge_labels]);

  pintarCifras([
    ["Nodos", numero.format(conexion.node_count)],
    ["Aristas", numero.format(conexion.edge_count)],
    ["JSON", (grafo.length / 1e6).toFixed(1) + " MB"],
    ["Motor", ms(motor)],
    ["Carga del grafo", ms(carga)],
  ]);

  // --- Tema claro y oscuro -------------------------------------------
  const raiz = document.documentElement;
  const botonTema = $("tema");
  const oscuroDelSistema = window.matchMedia("(prefers-color-scheme: dark)");
  const esOscuro = () =>
    raiz.dataset.tema ? raiz.dataset.tema === "oscuro" : oscuroDelSistema.matches;
  const rotularTema = () => {
    botonTema.textContent = esOscuro() ? "☀" : "☾";
  };
  rotularTema();

  const estilo = getComputedStyle(document.documentElement);
  const leerColores = (estilo) => ({
    red: estilo.getPropertyValue("--mapa-red").trim(),
    destacado: estilo.getPropertyValue("--magenta").trim(),
    papel: estilo.getPropertyValue("--papel").trim(),
    lugar: estilo.getPropertyValue("--lugar").trim(),
    reclamo: estilo.getPropertyValue("--reclamo").trim(),
    venue: estilo.getPropertyValue("--venue").trim(),
  });
  const colores = leerColores(estilo);
  // Al tocar un punto del mapa se muestra qué es, sobre el mismo punto.
  const tarjeta = $("tarjeta");
  const mostrarPunto = (tocado) => {
    if (!tocado) {
      tarjeta.hidden = true;
      return;
    }
    const { punto, x, y } = tocado;
    const titulo = document.createElement("b");
    titulo.textContent = punto.titulo ?? punto.clave;

    const partes = [];
    if (punto.capa === "lugares") partes.push(punto.detalle, punto.calle);
    if (punto.capa === "reclamos") partes.push(`reclamo ${punto.clave}`, punto.fecha);
    if (punto.capa === "venues") {
      partes.push("Foursquare", contar(punto.checkins ?? 0, "visita", "visitas"));
    }
    const detalle = document.createElement("span");
    detalle.textContent = partes.filter(Boolean).join(" · ");
    tarjeta.replaceChildren(titulo, detalle);

    if (punto.texto) {
      const cita = document.createElement("span");
      cita.className = "cita";
      const relato = punto.texto.trim();
      cita.textContent =
        relato.length > LARGO_RELATO
          ? `"${relato.slice(0, LARGO_RELATO).trimEnd()}…"`
          : `"${relato}"`;
      tarjeta.append(cita);
    }

    tarjeta.hidden = false;
    // La tarjeta se ancla al punto y se mantiene dentro del mapa.
    const caja = tarjeta.parentElement.getBoundingClientRect();
    const propia = tarjeta.getBoundingClientRect();
    const izquierda = Math.min(Math.max(8, x + 12), caja.width - propia.width - 8);
    const arriba = y + propia.height + 20 > caja.height ? y - propia.height - 12 : y + 12;
    tarjeta.style.left = `${izquierda}px`;
    tarjeta.style.top = `${Math.max(8, arriba)}px`;
  };

  const mapa = crearMapa($("lienzo"), conexion, colores, mostrarPunto);

  // El canvas no hereda los colores del tema, así que hay que repintarlo.
  const repintar = () => {
    Object.assign(colores, leerColores(getComputedStyle(raiz)));
    rotularTema();
    mapa.redibujar();
  };
  // El canvas no hereda las variables de color, hay que repintarlo a mano.
  oscuroDelSistema.addEventListener("change", repintar);
  botonTema.addEventListener("click", () => {
    const elegido = esOscuro() ? "claro" : "oscuro";
    raiz.dataset.tema = elegido;
    try {
      localStorage.setItem("tema", elegido);
    } catch (e) { /* almacenamiento bloqueado: el tema dura la sesión */ }
    repintar();
  });

  // Los tramos dibujados son menos que los del grafo: dos aristas entre las
  // mismas dos esquinas son la misma línea y se dibujan una vez.
  const leyendaModo = $("leyenda-modo");
  const anunciarModo = (nombre) => {
    leyendaModo.textContent =
      `Red de ${mapa.modos[nombre].etiqueta.toLowerCase()}: ` +
      `${numero.format(mapa.tramos(nombre))} tramos dibujados`;
  };

  const botonesModo = $("modos");
  let modoActivo = "auto";
  for (const [nombre, modo] of Object.entries(mapa.modos)) {
    const boton = document.createElement("button");
    boton.textContent = modo.etiqueta;
    boton.setAttribute("aria-pressed", String(nombre === modoActivo));
    boton.addEventListener("click", () => {
      modoActivo = nombre;
      mapa.verModo(nombre);
      anunciarModo(nombre);
      for (const otro of botonesModo.children) {
        otro.setAttribute("aria-pressed", String(otro === boton));
      }
    });
    botonesModo.append(boton);
  }
  const reiniciar = document.createElement("button");
  reiniciar.textContent = "Centrar";
  reiniciar.addEventListener("click", () => mapa.reiniciar());
  botonesModo.append(reiniciar);
  anunciarModo(modoActivo);

  // Las tres capas de puntos arrancan apagadas: con 1723 puntos sobre 2392
  // tramos, la red deja de leerse.
  const botonesCapa = $("capas");
  for (const [nombre, capa] of Object.entries(mapa.capas)) {
    const boton = document.createElement("button");
    boton.className = "capa";
    boton.dataset.capa = nombre;
    boton.textContent = `${capa.etiqueta} · ${numero.format(mapa.puntos(nombre))}`;
    boton.setAttribute("aria-pressed", "false");
    boton.addEventListener("click", () => {
      const visible = boton.getAttribute("aria-pressed") !== "true";
      boton.setAttribute("aria-pressed", String(visible));
      mapa.verCapa(nombre, visible);
    });
    botonesCapa.append(boton);
  }

  const pintadas = $("leyenda-destaque");

  // Al pulsar una constante se busca el nodo al que pertenece y se enciende en
  // el mapa. El tope evita traer miles de nodos por un valor muy repetido como
  // la categoría de un reclamo.
  const TOPE_INSPECCION = 300;
  const inspeccionar = ({ etiqueta, propiedad, valor }, contenedor) => {
    contenedor.hidden = false;
    contenedor.replaceChildren();

    const titulo = document.createElement("h3");
    titulo.textContent = `${etiqueta} con ${propiedad} = '${valor}'`;
    contenedor.append(titulo);

    const nota = document.createElement("span");
    nota.className = "nota";
    contenedor.append(nota);

    if (valor.includes("'")) {
      nota.textContent = "El valor trae una comilla y no se puede consultar así.";
      return;
    }

    const patron = `MATCH (n:${etiqueta}) WHERE n.${propiedad} = '${valor}'`;
    const cuenta = correr(`${patron} RETURN COUNT(n) AS total`);
    const traidos = correr(`${patron} RETURN n LIMIT ${TOPE_INSPECCION}`);
    if (cuenta.error || traidos.error) {
      nota.textContent = cuenta.error ?? traidos.error;
      return;
    }

    const total = cuenta.filas[0]?.total ?? 0;
    if (!total) {
      nota.textContent = "Ningún nodo tiene ese valor en este grafo.";
      mapa.limpiar();
      return;
    }

    const nodos = traidos.filas.map((f) => f.n);
    const encendido = mapa.destacarNodos(nodos);
    const ubicados = encendido.calles + encendido.puntos;
    nota.textContent =
      total === 1
        ? "Un nodo, encendido en el mapa."
        : `${numero.format(total)} nodos. El mapa enciende ` +
          `${contar(ubicados, "uno", "todos los que tienen coordenadas")} ` +
          "y abajo va el primero.";

    const props = nodos[0]?.props ?? {};
    const lista = document.createElement("dl");
    for (const [clave, valorProp] of Object.entries(props)) {
      const dt = document.createElement("dt");
      dt.textContent = clave;
      const dd = document.createElement("dd");
      dd.textContent =
        typeof valorProp === "number" && !SIN_FORMATO.has(clave)
          ? numero.format(valorProp)
          : String(valorProp);
      lista.append(dt, dd);
    }
    contenedor.append(lista);
  };

  // Cada consulta que termina enciende en el mapa las calles que nombra.
  const alTerminar = (consulta, resultado) => {
    const { calles, puntos, ambiguos } = mapa.destacar(
      resultado.filas,
      COLUMNAS_NO_UBICABLES,
    );
    const partes = [];
    if (calles) partes.push(contar(calles, "calle", "calles"));
    if (puntos) partes.push(contar(puntos, "punto", "puntos"));
    const muestra = document.createElement("span");
    muestra.className = "muestra";
    pintadas.replaceChildren(
      muestra,
      document.createTextNode(
        partes.length
          ? `${partes.join(" y ")} de la consulta ${consulta.numero}` +
            (ambiguos ? `, más ${ambiguos} con nombre repetido sin ubicar` : "")
          : `la consulta ${consulta.numero} no nombra nada ubicable`,
      ),
    );
  };

  const correr = (gql) => {
    try {
      const inicio = performance.now();
      const filas = conexion.execute(gql, SIN_TOPE);
      return { filas, milisegundos: performance.now() - inicio };
    } catch (e) {
      return { error: String(e?.message ?? e) };
    }
  };

  // El identificador de la plantilla no existe en esta área. Se elige el
  // reclamo por ruido cuya calle tenga más lugares, igual que `03-consultas.py`.
  const elegido = correr(
    "MATCH (r:Reclamo)-[:EN_CALLE]->(c:Calle)<-[:EN_CALLE]-(l:Lugar) " +
      "WHERE r.categoria = 'Ruido' " +
      "RETURN r.reporte_id AS id, COUNT(l) AS lugares " +
      "GROUP BY r ORDER BY lugares DESC LIMIT 1",
  );
  const ejemplo = elegido.filas?.[0]?.id ?? PLANTILLA;

  const aviso = $("aviso");
  const caja = document.createElement("p");
  caja.className = "aviso";
  caja.append(
    document.createTextNode("Las consultas que piden un reclamo concreto usan el "),
    document.createTextNode(`${ejemplo}, un reporte por ruido de esta comuna `),
    document.createTextNode("cuya calle tiene lugares mapeados. Los archivos traen "),
  );
  const plantilla = document.createElement("code");
  plantilla.textContent = PLANTILLA;
  caja.append(plantilla, document.createTextNode(" como plantilla."));
  aviso.append(caja);

  const lista = $("consultas");
  const ejecutables = [];
  for (const consulta of consultas) {
    consulta.gql = consulta.gql.replaceAll(`'${PLANTILLA}'`, `'${ejemplo}'`);
    consulta.faltan = [...etiquetasDe(consulta.gql)].filter((e) => !presentes.has(e));
    const { seccion, correr: ejecutar } = ficha(consulta, correr, alTerminar, inspeccionar);
    lista.append(seccion);
    if (ejecutar) ejecutables.push(ejecutar);
  }

  const todas = $("correr-todas");
  const total = $("total");
  todas.disabled = false;
  todas.addEventListener("click", async () => {
    todas.disabled = true;
    todas.textContent = "Corriendo…";
    total.textContent = "";
    let suma = 0;
    for (const ejecutar of ejecutables) {
      const resultado = await ejecutar();
      suma += resultado.milisegundos ?? 0;
    }
    todas.disabled = false;
    todas.textContent = "Correr todas";
    total.textContent = `${contar(ejecutables.length, "consulta", "consultas")} en ${ms(suma)}`;
  });
}

arrancar().catch((e) => {
  $("cifras").textContent = "No se pudo cargar el motor: " + (e?.message ?? e);
});
