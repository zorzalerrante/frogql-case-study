// Prototipo de aplicación sobre el grafo de Independencia: el mismo motor, el
// mismo grafo y las mismas consultas que la página de `web/`, sobre un
// mapa MapLibre con capas de deck.gl.
//
// Las constantes de cada consulta son parámetros: se cambian con controles o
// tocando el mapa, y la consulta vuelve a correr con cada cambio.
//
// El motor es froGQL compilado a WebAssembly, con backend en RAM. La entrada
// es el JSON que exporta `redosm/exportar.py`, porque el navegador no tiene
// sistema de archivos para abrir el `.gdb`.
import init, { open_json } from "../vendor/frogql_wasm.js";
import { MODOS, CAPAS, leerGrafo, ubicarFilas, esRuta, etiquetasDe, textoDeLista } from "../grafo.js";
import { parametrosDe, tramosDe, escribir, valoresDe } from "./parametros.js";
import { estiloEntintado } from "./tinte.js";

// El identificador que traen los .gql como plantilla. Los identificadores son
// correlativos por área, así que hay que reemplazarlo por uno que exista acá.
const PLANTILLA = "000050";
// Sin tope de filas, igual que en `03-consultas.py`: cada .gql declara su
// propio LIMIT, que se aplica después del ORDER BY.
const SIN_TOPE = 0;
// Opciones del parámetro LIMIT. El 0 quita la cláusula.
const LIMITES = [5, 10, 20, 50, 100, 0];
// Filas que se dibujan. La consulta corre completa.
const FILAS_VISIBLES = { escritorio: 50, movil: 20 };
// Celdas más largas que esto se dejan partir en varias líneas.
const LARGO_TEXTO = 60;
// Columnas cuyo valor no es un nombre de calle aunque coincida con uno. La
// comuna es el caso claro: "Independencia" es comuna y también calle.
const COLUMNAS_NO_UBICABLES = new Set(["comuna", "categoria", "tipo", "origen", "modo"]);
// Largo del relato de un reclamo en la lectura. Los de SOSAFE llegan a varios
// renglones.
const LARGO_RELATO = 220;
// Calles rotuladas a la vez. Con más, los nombres se tapan entre sí.
const TOPE_ROTULOS = 30;
// Distancia en píxeles a la que un toque todavía elige una calle o un punto.
const RADIO_TOQUE = 8;
// Las etiquetas del grafo que tienen capa de puntos, y el campo del punto que
// guarda cada identificador. Un parámetro sobre ese identificador se elige
// tocando el punto en el mapa. La `etiqueta` de un lugar no es única, pero es
// lo que escriben las consultas: un nombre se lee y un `osm_id` no.
const CAPA_DE = { Lugar: "lugares", Reclamo: "reclamos", Venue: "venues" };
const CAMPO_DE = { reporte_id: "clave", venue_id: "clave", osm_id: "ref", etiqueta: "clave" };
const NOMBRE_DE = { Lugar: "lugar", Reclamo: "reclamo", Venue: "venue", Calle: "calle" };
const MOVIL = window.matchMedia("(max-width: 700px)");
const SIN_MOVIMIENTO = window.matchMedia("(prefers-reduced-motion: reduce)");

const numero = new Intl.NumberFormat("es-CL");
const ms = (valor) => (valor < 10 ? valor.toFixed(1) : Math.round(valor)) + " ms";
const contar = (cantidad, singular, plural) =>
  `${numero.format(cantidad)} ${cantidad === 1 ? singular : plural}`;

/** el("div", { class: "x", onclick: fn }, [hijos]). El texto entra siempre como texto. */
function el(etiqueta, atributos = {}, hijos = []) {
  const e = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const h of [].concat(hijos)) {
    if (h === null || h === undefined || h === false) continue;
    e.append(typeof h === "string" ? document.createTextNode(h) : h);
  }
  return e;
}

function rotulo(codigo, texto, atributos = {}) {
  return el("div", { class: "rotulo", ...atributos }, [el("span", { class: "cod", text: codigo }), texto]);
}

/** Texto con los tramos entre comillas invertidas como código. */
function conCodigo(texto) {
  return texto.split("`").map((parte, i) => (i % 2 ? el("code", { text: parte }) : parte));
}

// --- Colores del mapa -------------------------------------------------
// deck.gl pide colores como [r, g, b, a]. Se leen de las variables del tema,
// normalizadas por el contexto 2D a `#rrggbb` o `rgba(...)`.
const ctx2d = document.createElement("canvas").getContext("2d");
function rgba(css) {
  ctx2d.fillStyle = "#000";
  ctx2d.fillStyle = css;
  const n = ctx2d.fillStyle;
  if (n.startsWith("#")) {
    return [1, 3, 5].map((i) => parseInt(n.slice(i, i + 2), 16)).concat(255);
  }
  const p = n.match(/[\d.]+/g).map(Number);
  return [p[0], p[1], p[2], Math.round((p[3] ?? 1) * 255)];
}
function leerColores() {
  const estilo = getComputedStyle(document.documentElement);
  const leer = (nombre) => rgba(estilo.getPropertyValue(nombre).trim());
  return {
    red: leer("--mapa-red"),
    destacado: leer("--destacado"),
    foco: leer("--foco"),
    tinta: leer("--tinta"),
    texto: leer("--texto"),
    fondo: leer("--fondo-hud"),
    lugar: leer("--lugar"),
    reclamo: leer("--reclamo"),
    venue: leer("--venue"),
  };
}

async function arrancar() {
  const aviso = el("div", { class: "hud aviso", role: "status", text: "Cargando el motor" });
  document.body.append(aviso);

  const marca = performance.now();
  await init();
  const tiempoMotor = performance.now() - marca;

  aviso.textContent = "Cargando el grafo";
  const [texto, consultas] = await Promise.all([
    fetch("../datos/independencia.json").then((r) => r.text()),
    fetch("../datos/consultas.json").then((r) => r.json()),
  ]);
  const inicioCarga = performance.now();
  const conexion = open_json(texto);
  const tiempoCarga = performance.now() - inicioCarga;
  const esquema = conexion.schema();
  const presentes = new Set([...esquema.node_labels, ...esquema.edge_labels]);
  const grafo = leerGrafo(conexion);

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
  for (const consulta of consultas) {
    consulta.gql = consulta.gql.replaceAll(`'${PLANTILLA}'`, `'${ejemplo}'`);
    consulta.faltan = [...etiquetasDe(consulta.gql)].filter((e) => !presentes.has(e));
    consulta.parametros = parametrosDe(consulta.gql);
    consulta.valores = consulta.parametros.map((p) => structuredClone(p.original));
    consulta.resultado = null;
  }

  // Los valores posibles de cada propiedad, que se consultan una vez.
  const cacheValores = new Map();
  const valoresPosibles = (etiqueta, propiedad) => {
    const llave = `${etiqueta}.${propiedad}`;
    if (!cacheValores.has(llave)) cacheValores.set(llave, valoresDe(correr, etiqueta, propiedad));
    return cacheValores.get(llave);
  };

  /** Si un parámetro se elige tocando un punto, la capa de ese punto. */
  const capaDelParametro = (p) =>
    p.tipo === "igual" && CAMPO_DE[p.propiedad] ? CAPA_DE[p.etiqueta] : null;
  const esCalle = (p) => p.tipo === "igual" && p.etiqueta === "Calle" && p.propiedad === "nombre";

  // --- Estado -----------------------------------------------------------
  const estado = {
    tema: document.documentElement.dataset.estilo,
    modo: "auto",
    capas: new Set(),
    // Lo que nombra el resultado, en magenta. `tramos` son las cuadras de una
    // ruta, que se encienden sin encender la calle entera.
    calles: new Set(),
    tramos: [],
    puntos: [],
    // Lo que se mira ahora (una fila o una calle tocada), en el color de foco.
    foco: { calles: new Set(), tramos: [], puntos: [] },
    seleccion: null,
    abierta: null,
  };
  let colores = leerColores();
  const esMovil = () => MOVIL.matches;
  const duracion = (valor) => (SIN_MOVIMIENTO.matches ? 0 : valor);

  // --- Mapa -------------------------------------------------------------
  const { limites } = grafo;
  const mapa = new maplibregl.Map({
    container: "mapa",
    center: [(limites.xmin + limites.xmax) / 2, (limites.ymin + limites.ymax) / 2],
    zoom: 13.5,
    minZoom: 11,
    maxZoom: 18,
    attributionControl: false,
  });
  mapa.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
  estiloEntintado(estado.tema).then((s) => mapa.setStyle(s));

  const superposicion = new deck.MapboxOverlay({
    interleaved: false,
    layers: [],
    pickingRadius: RADIO_TOQUE,
    // En el teléfono se dibuja a un píxel por píxel CSS.
    useDevicePixels: esMovil() ? 1 : true,
    onClick: (info) => alTocar(info),
    getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
  });
  mapa.addControl(superposicion);

  /** Las capas de puntos que se ven: las encendidas y la que pide la consulta abierta. */
  function capasVisibles() {
    const visibles = new Set(estado.capas);
    for (const p of estado.abierta?.parametros ?? []) {
      const capa = capaDelParametro(p);
      if (capa) visibles.add(capa);
    }
    return visibles;
  }

  /** El nombre de cada calle encendida, en el tramo más cercano a su centro. */
  function rotulos() {
    const porCalle = new Map();
    const encendida = (calle) => estado.foco.calles.has(calle) || estado.calles.has(calle);
    const enRuta = new Set([...estado.foco.tramos, ...estado.tramos]);
    const enFoco = new Set(estado.foco.tramos.map((t) => t.calle));
    for (const t of [...grafo.redes[estado.modo].filter((t) => encendida(t.calle)), ...enRuta]) {
      if (!porCalle.has(t.calle)) porCalle.set(t.calle, []);
      porCalle.get(t.calle).push([(t.x1 + t.x2) / 2, (t.y1 + t.y2) / 2]);
    }
    const salida = [];
    for (const [calle, medios] of porCalle) {
      const cx = medios.reduce((s, m) => s + m[0], 0) / medios.length;
      const cy = medios.reduce((s, m) => s + m[1], 0) / medios.length;
      let mejor = medios[0];
      for (const m of medios) {
        if (Math.hypot(m[0] - cx, m[1] - cy) < Math.hypot(mejor[0] - cx, mejor[1] - cy)) mejor = m;
      }
      // La calle en foco gana cuando dos nombres se tapan.
      const prioridad = estado.foco.calles.has(calle) || enFoco.has(calle) ? 1 : 0;
      salida.push({ posicion: mejor, texto: grafo.nombreDe.get(calle) ?? calle, prioridad });
    }
    return salida.sort((a, b) => b.prioridad - a.prioridad).slice(0, TOPE_ROTULOS);
  }

  const tenue = ([r, g, b, a]) => [r, g, b, Math.round(a * 0.35)];

  function dibujar() {
    const tramos = grafo.redes[estado.modo];
    const filtrar = (calles) => (calles.size ? tramos.filter((t) => calles.has(t.calle)) : []);
    const origen = (t) => [t.x1, t.y1];
    const destino = (t) => [t.x2, t.y2];
    const posicion = (p) => [p.x, p.y];
    const linea = (id, data, color, ancho, extra = {}) =>
      new deck.LineLayer({
        id, data, getSourcePosition: origen, getTargetPosition: destino, pickable: true,
        getColor: color, getWidth: ancho, widthUnits: "pixels", ...extra,
      });
    const puntos = (id, data, color, radio, extra = {}) =>
      new deck.ScatterplotLayer({
        id, data, getPosition: posicion, pickable: true, radiusUnits: "pixels", getRadius: radio,
        getFillColor: color, stroked: true, lineWidthUnits: "pixels", getLineWidth: 1,
        getLineColor: colores.tinta, ...extra,
      });
    const capas = [
      linea("red", tramos, colores.red, 1.4),
      linea("red-destacada", filtrar(estado.calles), colores.destacado, 4),
      // Las cuadras de una ruta vienen de cualquier modo: la consulta la arma
      // sobre las calles y no sobre la red que se está mirando.
      // Con una ruta elegida entre varias, las demás quedan tenues.
      linea("red-ruta", estado.tramos, estado.foco.tramos.length ? tenue(colores.destacado) : colores.destacado, 4),
      linea("red-foco", filtrar(estado.foco.calles), colores.foco, 6),
      linea("red-ruta-foco", estado.foco.tramos, colores.foco, 6),
      ...[...capasVisibles()].map((nombre) =>
        puntos(`capa-${nombre}`, grafo.capas[nombre], colores[CAPAS[nombre].color], 4),
      ),
      puntos("puntos-destacados", estado.puntos, colores.destacado, 6.5, { getLineWidth: 1.5 }),
      puntos("puntos-foco", estado.foco.puntos, colores.foco, 8, { getLineWidth: 2 }),
      new deck.ScatterplotLayer({
        id: "seleccion", data: estado.seleccion ? [estado.seleccion] : [], getPosition: posicion,
        radiusUnits: "pixels", getRadius: 12, filled: false, stroked: true,
        lineWidthUnits: "pixels", getLineWidth: 2.5, getLineColor: colores.texto,
      }),
      new deck.TextLayer({
        id: "rotulos", data: rotulos(), getPosition: (r) => r.posicion, getText: (r) => r.texto,
        characterSet: "auto", fontFamily: "Space Grotesk", fontWeight: 600, getSize: 14,
        getColor: colores.texto, background: true, getBackgroundColor: colores.fondo,
        backgroundPadding: [5, 3], getPixelOffset: [0, -14],
        // Un nombre que tapa a otro de más prioridad no se dibuja.
        extensions: [new deck.CollisionFilterExtension()], collisionTestProps: { sizeScale: 2 },
        getCollisionPriority: (r) => r.prioridad,
      }),
    ];
    superposicion.setProps({ layers: capas });
  }

  /** Lo que queda libre de bloques, para encuadrar ahí. */
  function margenes() {
    const abierta = estado.abierta && !ventana.hidden;
    return esMovil()
      ? { top: columna.offsetHeight + 16, bottom: (abierta ? ventana.offsetHeight : 0) + 16, left: 12, right: 12 }
      : { top: 30, bottom: 30, left: columna.offsetWidth + 40, right: (abierta ? ventana.offsetWidth + 16 : 0) + 30 };
  }
  const caja = (xs, ys) => [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];

  function encuadrar(tiempo = 600) {
    mapa.fitBounds(caja([limites.xmin, limites.xmax], [limites.ymin, limites.ymax]), {
      padding: margenes(), duration: duracion(tiempo),
    });
  }

  /** Lleva la cámara a lo que está en foco. */
  function irAlFoco() {
    const xs = [];
    const ys = [];
    for (const t of grafo.redes[estado.modo]) {
      if (estado.foco.calles.has(t.calle)) xs.push(t.x1, t.x2), ys.push(t.y1, t.y2);
    }
    for (const t of estado.foco.tramos) xs.push(t.x1, t.x2), ys.push(t.y1, t.y2);
    for (const p of estado.foco.puntos) xs.push(p.x), ys.push(p.y);
    if (!xs.length) return;
    mapa.fitBounds(caja(xs, ys), { padding: margenes(), maxZoom: 16.5, duration: duracion(500) });
  }

  // --- Toques en el mapa ------------------------------------------------
  function alTocar(info) {
    const objeto = info.picked ? info.object : null;
    if (objeto && info.layer.id.startsWith("red")) return elegirCalle(objeto.calle);
    if (objeto?.capa) return elegirPunto(objeto);
    cerrarLectura();
  }

  /** Si la consulta abierta tiene un parámetro que se llena con esto, lo llena. */
  function llenarParametro(prueba, valor) {
    const consulta = estado.abierta;
    const aptos = (consulta?.parametros ?? []).flatMap((q, j) => (prueba(q) ? [j] : []));
    if (!aptos.length) return false;
    // Con dos parámetros que aceptan lo mismo, como el origen y el destino de
    // una ruta, los toques se turnan entre ellos.
    const i = aptos.find((j) => j > (consulta.ultimoLleno ?? -1)) ?? aptos[0];
    consulta.ultimoLleno = i;
    consulta.valores[i] = valor;
    abrir(consulta, { correr: true });
    return true;
  }

  function elegirPunto(punto) {
    const p = estado.abierta?.parametros.find((q) => capaDelParametro(q) === punto.capa);
    const lleno = p ? llenarParametro((q) => q === p, String(punto[CAMPO_DE[p.propiedad]])) : false;
    // En el teléfono la lectura taparía la ventana que acaba de cambiar.
    if (lleno && esMovil()) {
      estado.seleccion = punto;
      dibujar();
      return;
    }
    mostrarPunto(punto);
  }

  function elegirCalle(calle) {
    const nombre = grafo.nombreDe.get(calle);
    if (!nombre) return;
    const lleno = llenarParametro(esCalle, nombre);
    estado.foco = { calles: new Set([calle]), tramos: [], puntos: [] };
    if (lleno && esMovil()) return dibujar();
    mostrarCalle(calle, nombre);
  }

  // --- 05 Lectura de lo tocado ------------------------------------------
  const lectura = el("section", { class: "hud lectura", "aria-live": "polite", hidden: true });
  document.body.append(lectura);

  function cerrarLectura() {
    estado.seleccion = null;
    lectura.hidden = true;
    dibujar();
  }

  /** Botones para abrir las consultas que aceptan este elemento como parámetro. */
  function consultasPara(prueba, valor) {
    // La consulta abierta ya recibió el valor al tocar el mapa.
    const aptas = consultas.filter((c) => c !== estado.abierta && !c.faltan.length && c.parametros.some(prueba));
    if (!aptas.length) return null;
    return el("div", { class: "relacionadas" }, [
      el("div", { class: "rotulo", text: "Consultar con este valor" }),
      ...aptas.map((consulta) =>
        el("button", {
          type: "button", class: "enlace-consulta",
          onclick: () => {
            const i = consulta.parametros.findIndex(prueba);
            // Un punto se nombra por distintos campos según la propiedad que
            // pida el parámetro, así que el valor puede depender de él.
            consulta.valores[i] = typeof valor === "function" ? valor(consulta.parametros[i]) : valor;
            abrir(consulta, { correr: true });
          },
        }, [el("span", { class: "n", text: consulta.numero }), consulta.titulo]),
      ),
    ]);
  }

  function mostrarLectura(codigo, tipo, titulo, detalle, extra = []) {
    lectura.replaceChildren(
      el("div", { class: "barra-lectura" }, [
        rotulo(codigo, tipo),
        el("button", { type: "button", class: "soltar", text: "Cerrar", onclick: cerrarLectura }),
      ]),
      el("h2", { text: titulo }),
      detalle ? el("p", { class: "sub", text: detalle }) : null,
      ...extra,
    );
    lectura.hidden = false;
  }

  function mostrarPunto(p) {
    estado.seleccion = p;
    dibujar();
    const partes = [];
    if (p.capa === "lugares") partes.push(p.detalle, p.calle);
    if (p.capa === "reclamos") partes.push(`Reclamo ${p.clave}`, p.fecha);
    if (p.capa === "venues") partes.push("Foursquare", contar(p.checkins ?? 0, "visita", "visitas"));
    const relato = p.texto?.trim();
    const id = (q) => capaDelParametro(q) === p.capa;
    mostrarLectura("05", CAPAS[p.capa].etiqueta, p.titulo ?? p.clave, partes.filter(Boolean).join(" · "), [
      relato
        ? el("p", {
            class: "cita",
            text: relato.length > LARGO_RELATO ? `"${relato.slice(0, LARGO_RELATO).trimEnd()}..."` : `"${relato}"`,
          })
        : null,
      consultasPara(id, (q) => String(p[CAMPO_DE[q.propiedad]])),
    ]);
  }

  function mostrarCalle(calle, nombre) {
    estado.seleccion = null;
    dibujar();
    const cuenta = (patron) =>
      correr(`MATCH ${patron} WHERE c.calle_id = '${calle}' RETURN COUNT(x) AS n`).filas?.[0]?.n ?? 0;
    const detalle = [
      contar(cuenta("(x:Reclamo)-[:EN_CALLE]->(c:Calle)"), "reclamo", "reclamos"),
      contar(cuenta("(x:Lugar)-[:EN_CALLE]->(c:Calle)"), "lugar", "lugares"),
      contar(cuenta("(x:Venue)-[:EN_CALLE]->(c:Calle)"), "venue", "venues"),
      contar(cuenta("(c:Calle)~[:CRUZA_CON]~(x:Calle)"), "calle que cruza", "calles que cruzan"),
    ].join(" · ");
    mostrarLectura("05", "Calle", nombre, detalle, [consultasPara(esCalle, nombre)]);
  }

  // --- Columna izquierda ----------------------------------------------
  const columna = el("div", { class: "columna-izq" });
  document.getElementById("app").append(columna);

  // 01 Grafo
  const botonTema = el("button", { type: "button", onclick: () => alternarTema() });
  const botonLista = el("button", {
    type: "button", class: "solo-movil", text: "Consultas", "aria-expanded": "false",
    onclick: () => mostrarLista(!document.body.classList.contains("con-lista")),
  });
  const mostrarLista = (visible) => {
    document.body.classList.toggle("con-lista", visible);
    botonLista.classList.toggle("activo", visible);
    botonLista.setAttribute("aria-expanded", String(visible));
  };
  const cifra = (etiqueta, valor) => el("div", {}, [el("dt", { text: etiqueta }), el("dd", { text: valor })]);
  columna.append(
    el("section", { class: "hud grafo", "aria-label": "Grafo" }, [
      rotulo("01", "Grafo en el navegador"),
      el("h1", { text: "froGQL · Independencia" }),
      el("p", {
        class: "sub",
        text: "El grafo entero se carga en froGQL compilado a WebAssembly. Las consultas corren acá, sin servidor.",
      }),
      el("dl", { class: "cifras" }, [
        cifra("Nodos", numero.format(conexion.node_count)),
        cifra("Aristas", numero.format(conexion.edge_count)),
        cifra("Calles", numero.format(grafo.nombreDe.size)),
        cifra("JSON", (texto.length / 1e6).toFixed(1) + " MB"),
        cifra("Motor", ms(tiempoMotor)),
        cifra("Carga", ms(tiempoCarga)),
      ]),
      el("div", { class: "botones" }, [
        botonLista,
        el("button", { type: "button", class: "solo-escritorio", text: "Encuadrar", onclick: () => encuadrar() }),
        botonTema,
        el("button", { type: "button", text: "Acerca de", onclick: () => acercaDe() }),
      ]),
    ]),
  );

  // 02 Red y capas
  const cuentaTramos = el("p", { class: "sub" });
  const botonesModo = Object.entries(MODOS).map(([nombre, modo]) =>
    el("button", {
      type: "button", text: modo.etiqueta, "aria-pressed": String(nombre === estado.modo),
      onclick: () => {
        estado.modo = nombre;
        botonesModo.forEach((b, i) => b.setAttribute("aria-pressed", String(Object.keys(MODOS)[i] === nombre)));
        anunciarModo();
        dibujar();
      },
    }),
  );
  const anunciarModo = () => {
    cuentaTramos.textContent = `${numero.format(grafo.redes[estado.modo].length)} tramos dibujados.`;
  };
  const botonesCapa = Object.entries(CAPAS).map(([nombre, capa]) =>
    el("button", {
      type: "button", style: `--marca: var(--${capa.color})`, "aria-pressed": "false",
      text: `${capa.etiqueta} ${numero.format(grafo.capas[nombre].length)}`,
      onclick: (ev) => {
        if (estado.capas.has(nombre)) estado.capas.delete(nombre);
        else estado.capas.add(nombre);
        ev.currentTarget.setAttribute("aria-pressed", String(estado.capas.has(nombre)));
        dibujar();
      },
    }),
  );
  const estadoResultado = el("span", { text: "Sin resultado en el mapa." });
  columna.append(
    el("section", { class: "hud red", "aria-label": "Red y capas" }, [
      rotulo("02", "Red y capas"),
      el("div", { class: "canal" }, [
        el("div", { class: "rotulo", text: "Modo" }),
        el("div", {}, [el("div", { class: "op" }, botonesModo), el("div", { class: "solo-escritorio" }, cuentaTramos)]),
      ]),
      // Las capas arrancan apagadas: con 1.723 puntos sobre la red, la red deja de leerse.
      el("div", { class: "canal solo-escritorio" }, [
        el("div", { class: "rotulo", text: "Puntos" }),
        el("div", { class: "op chips" }, botonesCapa),
      ]),
      el("p", { class: "estado", "aria-live": "polite" }, [el("span", { class: "muestra" }), estadoResultado]),
      el("p", {
        class: "pista solo-escritorio",
        text: "Toca una calle o un punto para ver qué es y qué consultas lo usan.",
      }),
    ]),
  );
  anunciarModo();

  // 03 Consultas
  const filasLista = new Map();
  const totalLista = el("span", { class: "num" });
  const botonTodas = el("button", { type: "button", text: "Correr todas", onclick: () => correrTodas() });
  columna.append(
    el("section", { class: "hud consultas", "aria-label": "Consultas" }, [
      rotulo("03", "Consultas GQL"),
      el(
        "ul",
        { class: "lista" },
        consultas.map((consulta) => {
          const tiempo = el("span", { class: "t" });
          const boton = el(
            "button",
            {
              type: "button",
              class: consulta.faltan.length ? "inactiva" : "",
              title: consulta.faltan.length ? `El grafo no tiene ${consulta.faltan.join(" ni ")}` : consulta.archivo,
              onclick: () => {
                mostrarLista(false);
                abrir(consulta, { correr: !consulta.resultado });
              },
            },
            [el("span", { class: "n", text: consulta.numero }), el("span", { text: consulta.titulo }), tiempo],
          );
          filasLista.set(consulta, { boton, tiempo });
          return el("li", {}, boton);
        }),
      ),
      el("div", { class: "pie-lista solo-escritorio" }, [botonTodas, totalLista]),
    ]),
  );

  // --- Resultado en el mapa --------------------------------------------
  function mostrarEnMapa(consulta, resultado) {
    const ubicado = ubicarFilas(grafo, resultado?.filas, COLUMNAS_NO_UBICABLES);
    estado.calles = ubicado.calles;
    estado.tramos = ubicado.tramos;
    estado.puntos = ubicado.puntos;
    estado.foco = { calles: new Set(), tramos: [], puntos: [] };
    const partes = [];
    if (ubicado.nombradas) partes.push(contar(ubicado.nombradas, "calle", "calles"));
    if (ubicado.puntos.length) partes.push(contar(ubicado.puntos.length, "punto", "puntos"));
    estadoResultado.textContent = partes.length
      ? `${partes.join(" y ")} de la consulta ${consulta.numero}` +
        (ubicado.ambiguos ? `, más ${ubicado.ambiguos} con nombre repetido sin ubicar.` : ".")
      : `La consulta ${consulta.numero} no nombra nada ubicable.`;
    dibujar();
  }

  function ejecutar(consulta) {
    const resultado = correr(escribir(consulta.gql, consulta.parametros, consulta.valores));
    consulta.resultado = resultado;
    filasLista.get(consulta).tiempo.textContent = resultado.error ? "error" : ms(resultado.milisegundos);
    mostrarEnMapa(consulta, resultado);
    return resultado;
  }

  async function correrTodas() {
    botonTodas.disabled = true;
    let suma = 0;
    let corridas = 0;
    for (const consulta of consultas) {
      if (consulta.faltan.length) continue;
      // Un cuadro entre consulta y consulta, para que la lista se repinte: el
      // motor corre en el hilo de la interfaz.
      await new Promise((listo) => requestAnimationFrame(listo));
      suma += ejecutar(consulta).milisegundos ?? 0;
      corridas += 1;
    }
    totalLista.textContent = `${contar(corridas, "consulta", "consultas")} en ${ms(suma)}`;
    botonTodas.disabled = false;
    if (estado.abierta) abrir(estado.abierta);
  }

  // --- 04 Ventana de la consulta ------------------------------------
  const ventana = el("section", { class: "hud ventana", role: "region", "aria-labelledby": "titulo-consulta", hidden: true });
  document.body.append(ventana);

  function cerrar() {
    if (estado.abierta) filasLista.get(estado.abierta).boton.classList.remove("activo");
    estado.abierta = null;
    ventana.hidden = true;
    document.body.classList.remove("con-ventana");
    dibujar();
    encuadrar();
  }

  /** El control de un parámetro. Cada cambio vuelve a correr la consulta. */
  function control(consulta, i) {
    const p = consulta.parametros[i];
    const cambiar = (valor) => {
      consulta.valores[i] = valor;
      abrir(consulta, { correr: true });
    };
    const id = `param-${consulta.numero}-${i}`;
    const etiqueta = (texto) => el("label", { for: id, class: "nombre-param", text: texto });

    if (p.tipo === "limite") {
      const opciones = [...new Set([...LIMITES, p.original])].sort((a, b) => (a || Infinity) - (b || Infinity));
      return el("div", { class: "param" }, [
        etiqueta("Filas (LIMIT)"),
        el("select", { id, onchange: (ev) => cambiar(Number(ev.target.value)) },
          opciones.map((n) => el("option", { value: n, selected: n === consulta.valores[i], text: n ? String(n) : "Sin límite" }))),
      ]);
    }

    if (p.tipo === "lista") {
      const elegidos = new Set(consulta.valores[i]);
      const posibles = valoresPosibles(p.etiqueta, p.propiedad);
      const mostrados = [...new Set([...p.original, ...consulta.valores[i]])];
      const restantes = posibles.filter((v) => !mostrados.includes(v.valor));
      return el("fieldset", { class: "param" }, [
        el("legend", { class: "nombre-param", text: `${p.etiqueta}.${p.propiedad} en la lista` }),
        el("div", { class: "fichas" }, mostrados.map((valor) =>
          el("label", { class: "ficha" }, [
            el("input", {
              type: "checkbox", checked: elegidos.has(valor),
              onchange: (ev) => {
                const nuevos = mostrados.filter((v) => (v === valor ? ev.target.checked : elegidos.has(v)));
                cambiar(nuevos);
              },
            }),
            valor,
          ]))),
        restantes.length
          ? el("select", {
              "aria-label": `Agregar ${p.propiedad}`,
              onchange: (ev) => ev.target.value && cambiar([...consulta.valores[i], ev.target.value]),
            }, [
              el("option", { value: "", text: "Agregar otro valor" }),
              ...restantes.map((v) => el("option", { value: v.valor, text: `${v.valor} (${numero.format(v.nodos)})` })),
            ])
          : null,
      ]);
    }

    const capa = capaDelParametro(p);
    if (capa) {
      // Un identificador: se elige tocando el punto o paso a paso.
      const campo = CAMPO_DE[p.propiedad];
      // Un valor por paso: los lugares sin nombre comparten etiqueta y, sin
      // quitar los repetidos, el paso quedaría detenido en el primero.
      const unicos = new Map(grafo.capas[capa].map((q) => [String(q[campo]), q]));
      const puntos = [...unicos.values()].sort((a, b) => String(a[campo]).localeCompare(String(b[campo])));
      const actual = puntos.findIndex((q) => String(q[campo]) === consulta.valores[i]);
      const punto = puntos[actual];
      const paso = (d) => cambiar(String(puntos[(actual + d + puntos.length) % puntos.length][campo]));
      return el("div", { class: "param" }, [
        el("div", { class: "nombre-param", text: `${p.etiqueta}.${p.propiedad}` }),
        el("div", { class: "elegido" }, [
          el("b", { text: consulta.valores[i] }),
          punto ? ` · ${[punto.titulo ?? punto.detalle, punto.fecha].filter(Boolean).join(" · ")}` : "",
        ]),
        el("div", { class: "botones" }, [
          el("button", { type: "button", text: `${NOMBRE_DE[p.etiqueta]} anterior`, onclick: () => paso(-1) }),
          el("button", { type: "button", text: `${NOMBRE_DE[p.etiqueta]} siguiente`, onclick: () => paso(1) }),
        ]),
        el("p", { class: "pista", text: `O toca un ${NOMBRE_DE[p.etiqueta]} en el mapa.` }),
      ]);
    }

    const posibles = valoresPosibles(p.etiqueta, p.propiedad);
    const ordenados = esCalle(p) ? [...posibles].sort((a, b) => a.valor.localeCompare(b.valor, "es")) : posibles;
    return el("div", { class: "param" }, [
      etiqueta(`${p.etiqueta}.${p.propiedad}`),
      el("select", { id, onchange: (ev) => cambiar(ev.target.value) },
        ordenados.map((v) => el("option", {
          value: v.valor, selected: v.valor === consulta.valores[i],
          text: esCalle(p) ? v.valor : `${v.valor} (${numero.format(v.nodos)})`,
        }))),
      esCalle(p) ? el("p", { class: "pista", text: "O toca una calle en el mapa." }) : null,
    ]);
  }

  /** La tabla del resultado. Cada fila enciende en el mapa lo que nombra. */
  function tabla(filas, visibles) {
    const mostradas = filas.slice(0, visibles);
    const columnas = [...new Set(mostradas.flatMap((fila) => Object.keys(fila)))];
    let elegida = null;
    const enfocar = (fila, mover) => {
      const ubicado = fila
        ? ubicarFilas(grafo, [fila], COLUMNAS_NO_UBICABLES)
        : { calles: new Set(), tramos: [], puntos: [] };
      estado.foco = { calles: ubicado.calles, tramos: ubicado.tramos, puntos: ubicado.puntos };
      dibujar();
      if (mover) irAlFoco();
    };
    const cuerpo = mostradas.map((fila) => {
      const tr = el("tr", { tabindex: "0" }, columnas.map((columna) => {
        const valor = fila[columna];
        const texto =
          valor === null || valor === undefined
            ? "s/d"
            : typeof valor === "number"
              ? numero.format(valor)
              : Array.isArray(valor) || typeof valor === "object"
                ? textoDeLista(valor)
                : String(valor);
        return el("td", { class: texto.length > LARGO_TEXTO ? "largo" : "", text: texto });
      }));
      const elegir = () => {
        elegida?.classList.remove("elegida");
        elegida = tr;
        tr.classList.add("elegida");
        enfocar(fila, true);
      };
      tr.addEventListener("click", elegir);
      tr.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          elegir();
        }
      });
      if (!esMovil()) tr.addEventListener("mouseenter", () => enfocar(fila, false));
      return tr;
    });
    // Si las filas son rutas, como los empates de la 06, la primera queda
    // elegida: el mapa la muestra sobre las demás.
    if (esRuta(mostradas[0])) {
      elegida = cuerpo[0];
      elegida.classList.add("elegida");
      enfocar(mostradas[0], false);
    }
    const cuerpoTabla = el("tbody", {}, cuerpo);
    // Al salir de la tabla vuelve la fila elegida, si hay.
    cuerpoTabla.addEventListener("mouseleave", () => enfocar(elegida ? mostradas[cuerpo.indexOf(elegida)] : null, false));
    return el("div", { class: "tabla" }, el("table", {}, [
      el("thead", {}, el("tr", {}, columnas.map((c) => el("th", { scope: "col", text: c })))),
      cuerpoTabla,
    ]));
  }

  function abrir(consulta, { correr: correrAhora = false } = {}) {
    const recienAbierta = !estado.abierta;
    if (estado.abierta) filasLista.get(estado.abierta).boton.classList.remove("activo");
    estado.abierta = consulta;
    filasLista.get(consulta).boton.classList.add("activo");
    document.body.classList.add("con-ventana");
    const scroll = ventana.querySelector(".cuerpo")?.scrollTop ?? 0;
    const misma = ventana.dataset.consulta === consulta.numero;

    const indice = consultas.indexOf(consulta);
    const vecina = (paso) => consultas[(indice + paso + consultas.length) % consultas.length];
    const salida = el("div", { "aria-live": "polite" });
    const tiempo = el("span", { class: "t" });

    const pintarResultado = (resultado) => {
      salida.replaceChildren();
      if (!resultado) return;
      tiempo.textContent = resultado.error ? "" : ms(resultado.milisegundos);
      if (resultado.error) {
        salida.append(el("pre", { class: "error", text: resultado.error }));
      } else if (!resultado.filas.length) {
        salida.append(el("p", { class: "pie-tabla", text: "Sin filas." }));
      } else {
        const visibles = esMovil() ? FILAS_VISIBLES.movil : FILAS_VISIBLES.escritorio;
        const total = resultado.filas.length;
        salida.append(
          el("p", {
            class: "pie-tabla",
            text:
              (total > visibles ? `${visibles} de ${numero.format(total)} filas.` : contar(total, "fila.", "filas.")) +
              " Toca una fila para verla en el mapa.",
          }),
          tabla(resultado.filas, visibles),
        );
      }
    };

    // El texto de la consulta con los valores actuales marcados.
    const codigo = el("pre", { class: "codigo" },
      tramosDe(consulta.gql, consulta.parametros, consulta.valores).map((t) =>
        t.indice === undefined ? t.texto : el("mark", { text: t.texto })));
    const cambiada = consulta.valores.some((v, i) => JSON.stringify(v) !== JSON.stringify(consulta.parametros[i].original));

    const cuerpo = [
      el("h2", { id: "titulo-consulta", text: consulta.titulo }),
      consulta.explicacion ? el("p", { class: "explicacion" }, conCodigo(consulta.explicacion)) : null,
    ];
    if (consulta.faltan.length) {
      cuerpo.push(
        el("p", {
          class: "nota vacia",
          text:
            `El grafo cargado no tiene ${consulta.faltan.join(" ni ")}, así que esta consulta no ` +
            "devuelve filas. Se agregan con 01-preparar-datos.py --con-censo.",
        }),
        codigo,
      );
    } else {
      cuerpo.push(
        consulta.parametros.length
          ? el("div", { class: "parametros" }, [
              el("div", { class: "rotulo", text: "Parámetros" }),
              ...consulta.parametros.map((_, i) => control(consulta, i)),
              cambiada
                ? el("button", {
                    type: "button", text: "Volver a los valores del archivo",
                    onclick: () => {
                      consulta.valores = consulta.parametros.map((p) => structuredClone(p.original));
                      abrir(consulta, { correr: true });
                    },
                  })
                : null,
            ])
          : el("p", { class: "nota vacia", text: "Esta consulta no tiene parámetros." }),
        el("details", { class: "texto" }, [el("summary", {}, [`Texto de ${consulta.archivo}`, tiempo]), codigo]),
        salida,
      );
    }

    ventana.replaceChildren(
      el("div", { class: "barra" }, [
        el("div", { class: "rotulo" }, [
          el("span", { class: "cod", text: "04" }),
          `Consulta ${consulta.numero}`,
        ]),
        el("button", { type: "button", text: "Anterior", "aria-label": "Consulta anterior", onclick: () => abrir(vecina(-1), { correr: !vecina(-1).resultado }) }),
        el("button", { type: "button", text: "Siguiente", "aria-label": "Consulta siguiente", onclick: () => abrir(vecina(1), { correr: !vecina(1).resultado }) }),
        el("button", { type: "button", text: "Cerrar", onclick: cerrar }),
      ]),
      el("div", { class: "cuerpo" }, cuerpo),
    );
    ventana.dataset.consulta = consulta.numero;
    ventana.hidden = false;
    // Al cambiar un parámetro la ventana se rehace entera: se conserva el
    // desplazamiento para que el control tocado no salte.
    if (misma) ventana.querySelector(".cuerpo").scrollTop = scroll;
    // La ventana tapa parte del mapa: la comuna se corre a lo que queda libre.
    if (recienAbierta) encuadrar();
    if (consulta.faltan.length) {
      dibujar();
      return;
    }
    pintarResultado(correrAhora ? ejecutar(consulta) : consulta.resultado);
    if (!correrAhora && consulta.resultado) mostrarEnMapa(consulta, consulta.resultado);
    if (!consulta.resultado) dibujar();
  }

  // --- Tema -----------------------------------------------------------
  const rotularTema = () => { botonTema.textContent = estado.tema === "oscuro" ? "Tema claro" : "Tema oscuro"; };
  function alternarTema() {
    estado.tema = estado.tema === "oscuro" ? "claro" : "oscuro";
    document.documentElement.dataset.estilo = estado.tema;
    try { localStorage.setItem("tema-prototipo", estado.tema); } catch (e) { /* almacenamiento bloqueado */ }
    rotularTema();
    colores = leerColores();
    estiloEntintado(estado.tema).then((s) => mapa.setStyle(s));
    dibujar();
  }
  rotularTema();

  // --- Acerca de ------------------------------------------------------
  function acercaDe() {
    const previo = document.activeElement;
    const fondo = el("div", { class: "modal-fondo", onclick: (ev) => { if (ev.target === fondo) quitar(); } });
    const alEscape = (ev) => { if (ev.key === "Escape") quitar(); };
    const quitar = () => {
      fondo.remove();
      document.removeEventListener("keydown", alEscape);
      previo?.focus();
    };
    document.addEventListener("keydown", alEscape);
    const botonCerrar = el("button", { type: "button", class: "cerrar", text: "Cerrar", onclick: quitar });
    fondo.append(
      el("div", { class: "hud modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "titulo-acerca" }, [
        botonCerrar,
        el("h2", { id: "titulo-acerca", text: "froGQL · Independencia" }),
        el("p", {
          text:
            "Esta página carga en el navegador el grafo de propiedades de la comuna de Independencia " +
            "y lo consulta con froGQL compilado a WebAssembly. Las consultas son los archivos " +
            "consultas/*.gql del repositorio, y cada resultado se enciende sobre la red vial.",
        }),
        el("div", { class: "rotulo", text: "El modelo" }),
        el("p", {
          text:
            "Las intersecciones son nodos y los tramos son aristas, una red por modo. La calle con " +
            "nombre también es un nodo, así que la consulta por los lugares de la misma calle que " +
            "un reclamo se escribe como un patrón de dos aristas.",
        }),
        el("pre", {
          text:
            "(:Interseccion) -[:CONECTA_AUTO]-> (:Interseccion)\n" +
            "(:Interseccion) ~[:CONECTA_BICI|CONECTA_PEATON]~ (:Interseccion)\n" +
            "(:Interseccion|:Lugar|:Reclamo|:Venue) -[:EN_CALLE]-> (:Calle)\n" +
            "(:Calle) ~[:CRUZA_CON]~ (:Calle)\n" +
            "(:Reclamo) -[:CERCA_DE]-> (:Lugar)\n" +
            "(:Lugar|:Reclamo|:Venue) -[:EN_ZONA]-> (:ZonaCensal)",
        }),
        el("div", { class: "rotulo", text: "Cómo se usa" }),
        el("p", {
          text:
            "El bloque 03 lista las consultas. Al abrir una, la ventana 04 muestra sus parámetros: " +
            "las constantes del archivo, que se cambian con los controles y vuelven a correr la " +
            "consulta. Un reclamo o una calle también se eligen tocándolos en el mapa. Cada fila " +
            "del resultado se enciende en el mapa al tocarla. Al tocar un elemento del mapa sin " +
            "consulta abierta, el bloque 05 muestra qué es y qué consultas lo aceptan.",
        }),
        el("div", { class: "rotulo", text: "Fuentes" }),
        el("p", {
          text:
            "Red vial y lugares de OpenStreetMap. Reclamos de SOSAFE. Venues del dataset de check-ins " +
            "de Foursquare. Mapa base de CARTO.",
        }),
        el("p", {}, [
          el("a", { href: "../", text: "Versión de una columna, con edición de consultas" }),
          " · ",
          el("a", { href: "https://github.com/zorzalerrante/frogql-case-study", text: "Repositorio" }),
        ]),
      ]),
    );
    document.body.append(fondo);
    botonCerrar.focus();
  }

  // Escape cierra lo que esté encima: la lectura, la lista o la ventana.
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || document.querySelector(".modal-fondo")) return;
    if (!lectura.hidden) cerrarLectura();
    else if (document.body.classList.contains("con-lista")) mostrarLista(false);
    else if (estado.abierta) cerrar();
  });

  // --- Arranque -------------------------------------------------------
  aviso.remove();
  await document.fonts.load('600 14px "Space Grotesk"').catch(() => null);
  dibujar();
  encuadrar(0);
  window.addEventListener("resize", () => mapa.resize());
}

arrancar().catch((e) => {
  const aviso = document.querySelector(".aviso") ?? document.body.appendChild(el("div", { class: "hud aviso" }));
  aviso.textContent = "No se pudo cargar el motor: " + (e?.message ?? e);
});
