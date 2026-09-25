// Lectura del grafo que comparten las dos páginas: la red por modo, las capas
// de puntos, las constantes de cada consulta y la ubicación en el mapa de lo
// que nombra un resultado. No dibuja nada.
//
// La geometría no viene de un archivo aparte ni de un servidor de mapas: sale
// de consultar el grafo. Cada tramo es un par de intersecciones con `lon` y
// `lat`, y el `calle_id` que trae la arista permite encender las calles que
// nombra el resultado de una consulta. El grafo no guarda la geometría
// intermedia de cada way, así que una curva larga se dibuja como cuerda.

export const MODOS = {
  auto: { etiqueta: "Auto", arista: "CONECTA_AUTO" },
  bici: { etiqueta: "Bici", arista: "CONECTA_BICI" },
  peaton: { etiqueta: "Peatón", arista: "CONECTA_PEATON" },
};

// Las tres capas de puntos que cuelgan de la red. La clave es la propiedad por
// la que se reconoce un punto en el resultado de una consulta: los lugares por
// su etiqueta, los reclamos por su identificador, los venues por el suyo.
export const CAPAS = {
  lugares: {
    etiqueta: "Lugares",
    color: "lugar",
    // `ref` es el identificador propio, que sirve para pegarle su calle.
    consulta:
      "MATCH (n:Lugar) RETURN n.lon AS x, n.lat AS y, n.etiqueta AS clave, " +
      "n.osm_id AS ref, n.categoria AS detalle",
    conCalle: "MATCH (n:Lugar)-[:EN_CALLE]->(c:Calle) RETURN n.osm_id AS ref, c.nombre AS calle",
  },
  reclamos: {
    etiqueta: "Reclamos",
    color: "reclamo",
    consulta:
      "MATCH (n:Reclamo) RETURN n.lon AS x, n.lat AS y, n.reporte_id AS clave, " +
      "n.reporte_id AS ref, n.categoria AS titulo, n.fecha AS fecha, n.descripcion AS texto",
    // La calle del reclamo es donde empieza la ruta de la 11.
    conCalle: "MATCH (n:Reclamo)-[:EN_CALLE]->(c:Calle) RETURN n.reporte_id AS ref, c.nombre AS calle",
  },
  venues: {
    etiqueta: "Venues",
    color: "venue",
    // Los venues de Foursquare no traen nombre, así que el título es su
    // categoría y el identificador no se muestra.
    consulta:
      "MATCH (n:Venue) RETURN n.lon AS x, n.lat AS y, n.venue_id AS clave, " +
      "n.categoria AS titulo, n.checkins AS checkins",
  },
};

/** Lee los tramos de un modo, una vez cada uno. */
export function tramosDe(conexion, arista) {
  const filas = conexion.execute(
    `MATCH (a:Interseccion)-[e:${arista}]-(b:Interseccion) ` +
      "RETURN a.lon AS x1, a.lat AS y1, b.lon AS x2, b.lat AS y2, e.calle_id AS calle",
    0,
  );
  // El patrón sin sentido devuelve cada tramo una vez por extremo. Se deja una
  // sola copia, con la clave ordenada para que los dos sentidos colapsen.
  const vistos = new Set();
  const tramos = [];
  for (const f of filas) {
    const clave =
      f.x1 < f.x2 || (f.x1 === f.x2 && f.y1 <= f.y2)
        ? `${f.x1},${f.y1},${f.x2},${f.y2}`
        : `${f.x2},${f.y2},${f.x1},${f.y1}`;
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    tramos.push({ x1: f.x1, y1: f.y1, x2: f.x2, y2: f.y2, calle: f.calle });
  }
  return tramos;
}

/** Lee los puntos de una capa con lo que hace falta para mostrarlos.
 *
 * Los lugares llevan además la calle a la que pertenecen. Su etiqueta no los
 * identifica: en la comuna hay 37 nombres compartidos por 105 lugares, entre
 * ellos nueve parques sin nombre y siete Copec. La calle separa a los
 * homónimos cuando el resultado de una consulta la nombra.
 */
export function puntosDe(conexion, nombre, capa) {
  const puntos = conexion.execute(capa.consulta, 0);
  for (const p of puntos) p.capa = nombre;
  if (!capa.conCalle) return puntos;

  const calles = new Map();
  for (const f of conexion.execute(capa.conCalle, 0)) calles.set(f.ref, f.calle);
  for (const p of puntos) p.calle = calles.get(p.ref);
  return puntos;
}

/**
 * Lee del grafo todo lo que se dibuja y arma los índices para volver de un
 * resultado a la geometría.
 */
export function leerGrafo(conexion) {
  const redes = {};
  for (const [nombre, modo] of Object.entries(MODOS)) {
    redes[nombre] = tramosDe(conexion, modo.arista);
  }

  const capas = {};
  // Para volver de una coordenada al punto que la ocupa.
  const porCoordenada = new Map();
  // Un punto se puede nombrar de varias formas y un nombre puede repetirse
  // entre lugares, así que el índice guarda listas.
  const porClave = new Map();
  for (const [nombre, capa] of Object.entries(CAPAS)) {
    capas[nombre] = puntosDe(conexion, nombre, capa);
    for (const punto of capas[nombre]) {
      porCoordenada.set(`${punto.x},${punto.y}`, punto);
      if (typeof punto.clave !== "string") continue;
      const llave = punto.clave.toLowerCase();
      if (!porClave.has(llave)) porClave.set(llave, []);
      porClave.get(llave).push(punto);
    }
  }

  // Índice de nombre a identificador, para traducir lo que devuelven las
  // consultas, que hablan de nombres, a lo que llevan los tramos.
  const porNombre = new Map();
  const nombreDe = new Map();
  // Un nombre puede ser de varias calles: los tramos homónimos que no se tocan
  // son calles distintas. `porNombre` guarda una, la que se enciende entera, y
  // `homonimas` todas, para que una ruta encuentre la que de verdad recorre.
  const homonimas = new Map();
  for (const c of conexion.execute("MATCH (c:Calle) RETURN c.calle_id AS id, c.nombre AS nombre", 0)) {
    const llave = c.nombre.toLowerCase();
    porNombre.set(llave, c.id);
    nombreDe.set(c.id, c.nombre);
    if (!homonimas.has(llave)) homonimas.set(llave, []);
    homonimas.get(llave).push(c.id);
  }

  const cuadras = indiceDeCuadras(redes);

  const limites = Object.values(redes)
    .flat()
    .reduce(
      (l, t) => ({
        xmin: Math.min(l.xmin, t.x1, t.x2),
        xmax: Math.max(l.xmax, t.x1, t.x2),
        ymin: Math.min(l.ymin, t.y1, t.y2),
        ymax: Math.max(l.ymax, t.y1, t.y2),
      }),
      { xmin: Infinity, xmax: -Infinity, ymin: Infinity, ymax: -Infinity },
    );

  return { redes, capas, porCoordenada, porClave, porNombre, homonimas, nombreDe, limites, cuadras };
}

const claveNodo = (x, y) => `${x},${y}`;

// Metros entre dos coordenadas, con la longitud comprimida por la latitud.
// A la escala de una comuna la aproximación plana basta.
const metros = (x1, y1, x2, y2) => {
  const cos = Math.cos((((y1 + y2) / 2) * Math.PI) / 180);
  return Math.hypot((x2 - x1) * cos, y2 - y1) * 111_320;
};

/**
 * Los tramos de las tres redes indexados por intersección y por calle, para
 * reconstruir una ruta cuadra por cuadra. Un tramo que aparece en varios modos
 * se guarda una vez.
 */
function indiceDeCuadras(redes) {
  const vecinos = new Map();
  const callesDe = new Map();
  const nodosDe = new Map();
  const vistos = new Set();
  const anotar = (mapa, llave, valor) => {
    if (!mapa.has(llave)) mapa.set(llave, new Set());
    mapa.get(llave).add(valor);
  };
  for (const t of Object.values(redes).flat()) {
    if (!t.calle) continue;
    const a = claveNodo(t.x1, t.y1);
    const b = claveNodo(t.x2, t.y2);
    const clave = a < b ? `${a};${b}` : `${b};${a}`;
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    const largo = metros(t.x1, t.y1, t.x2, t.y2);
    for (const [desde, hacia] of [[a, b], [b, a]]) {
      if (!vecinos.has(desde)) vecinos.set(desde, []);
      vecinos.get(desde).push({ hacia, calle: t.calle, largo, tramo: t });
      anotar(callesDe, desde, t.calle);
      anotar(nodosDe, t.calle, desde);
    }
  }
  return { vecinos, callesDe, nodosDe };
}

/**
 * El camino más corto entre dos intersecciones sin salir de una calle, o por
 * cualquier tramo si `calle` es null.
 */
function porLaCalle(cuadras, desde, hasta, calle) {
  if (desde === hasta) return { largo: 0, tramos: [] };
  // Una calle tiene a lo sumo unos cientos de intersecciones: Dijkstra con
  // búsqueda lineal del mínimo alcanza.
  const distancia = new Map([[desde, 0]]);
  const previo = new Map();
  const abiertos = new Set([desde]);
  const cerrados = new Set();
  while (abiertos.size) {
    let actual = null;
    for (const n of abiertos) if (actual === null || distancia.get(n) < distancia.get(actual)) actual = n;
    abiertos.delete(actual);
    cerrados.add(actual);
    if (actual === hasta) break;
    for (const v of cuadras.vecinos.get(actual) ?? []) {
      if ((calle !== null && v.calle !== calle) || cerrados.has(v.hacia)) continue;
      const nueva = distancia.get(actual) + v.largo;
      if (nueva < (distancia.get(v.hacia) ?? Infinity)) {
        distancia.set(v.hacia, nueva);
        previo.set(v.hacia, { desde: actual, tramo: v.tramo });
        abiertos.add(v.hacia);
      }
    }
  }
  if (!previo.has(hasta)) return null;
  const tramos = [];
  for (let n = hasta; n !== desde; n = previo.get(n).desde) tramos.push(previo.get(n).tramo);
  return { largo: distancia.get(hasta), tramos: tramos.reverse() };
}

/** La intersección de una calle más cercana a un punto suelto. */
function entradaALaCalle(cuadras, punto, calle) {
  let mejor = null;
  let menor = Infinity;
  for (const nodo of cuadras.nodosDe.get(calle) ?? []) {
    const [x, y] = nodo.split(",").map(Number);
    const d = metros(punto.x, punto.y, x, y);
    if (d < menor) (menor = d), (mejor = nodo);
  }
  return mejor && { nodo: mejor, largo: menor };
}

/**
 * Las esquinas que trae una fila, en el orden en que se recorren.
 *
 * El motor del navegador entrega las columnas en orden alfabético, así que el
 * orden no sale de ahí. Sale de cómo escriben la ruta los `.gql`: la lista del
 * grupo que se repite trae las esquinas intermedias en orden, y una esquina
 * suelta, como la `y` de la 06, es la última.
 */
function esquinasDe(fila) {
  const esInterseccion = (v) => v?.labels?.includes("Interseccion");
  const clave = (v) => claveNodo(v.props.lon, v.props.lat);
  const valores = Object.values(fila);
  const enLista = valores.filter(Array.isArray).flat().filter(esInterseccion);
  const sueltas = valores.filter((v) => !Array.isArray(v) && esInterseccion(v));
  return [...enLista, ...sueltas].map(clave);
}

/**
 * Si la fila es una ruta. Una ruta que no dobla trae la lista de esquinas
 * vacía, y ahí el tipo no se ve: por eso la columna vacía tiene que llamarse
 * `esquinas`, como en los `.gql` del repositorio.
 *
 * Cuando un resultado trae varias rutas, como los empates de la 06, las
 * páginas encienden todas tenues y una a la vez.
 */
export const esRuta = (fila) =>
  esquinasDe(fila ?? {}).length > 0 || (Array.isArray(fila?.esquinas) && !fila.esquinas.length);

/**
 * Reconstruye cuadra por cuadra la ruta de una fila que trae las esquinas
 * donde se dobla. Entre dos esquinas seguidas se camina por la calle que las
 * une, y los puntos de la fila, como un reclamo y un local, se conectan con el
 * extremo de la ruta que les queda más cerca por su propia calle.
 *
 * Devuelve los tramos y las calles que recorren, para que esas calles no se
 * enciendan enteras.
 */
function rutaDeFila(grafo, esquinas, callesFila, puntosFila) {
  const { cuadras } = grafo;
  const tramos = [];
  const usadas = new Set();
  const candidatas = (nodo) => [...(cuadras.callesDe.get(nodo) ?? [])];

  const mejorTramo = (desde, hasta, calles) => {
    let mejor = null;
    for (const calle of calles) {
      const ruta = porLaCalle(cuadras, desde, hasta, calle);
      if (ruta && (!mejor || ruta.largo < mejor.largo)) mejor = { ...ruta, calle };
    }
    return mejor;
  };

  for (let i = 0; i + 1 < esquinas.length; i++) {
    const compartidas = candidatas(esquinas[i]).filter((c) => cuadras.callesDe.get(esquinas[i + 1])?.has(c));
    const mejor = mejorTramo(esquinas[i], esquinas[i + 1], compartidas);
    if (mejor) {
      tramos.push(...mejor.tramos);
      usadas.add(mejor.calle);
      continue;
    }
    // Una esquina puede colgar de la calle por un enlace con otro nombre, como
    // el ramal que une las dos calzadas de una avenida. Entonces se camina por
    // cualquier tramo y la calle se da por recorrida igual.
    const libre = porLaCalle(cuadras, esquinas[i], esquinas[i + 1], null);
    if (!libre) continue;
    tramos.push(...libre.tramos);
    for (const calle of compartidas) usadas.add(calle);
  }

  // Un punto suelto entra a la ruta por su propia calle, la de su EN_CALLE.
  // Si la página no la conoce, por la calle de la fila que tiene una
  // intersección más cerca. Si esa calle está cortada entre el punto y la
  // esquina, se camina por cualquier tramo desde la entrada.
  const conectar = (punto, extremo) => {
    const propia = (c) => punto.calle && grafo.nombreDe.get(c)?.toLowerCase() === punto.calle.toLowerCase();
    const entradas = candidatas(extremo)
      .filter((c) => callesFila.has(c))
      .map((calle) => ({ calle, entrada: entradaALaCalle(cuadras, punto, calle) }))
      .filter((c) => c.entrada)
      .sort((a, b) => propia(b.calle) - propia(a.calle) || a.entrada.largo - b.entrada.largo);
    if (!entradas.length) return null;
    const { calle, entrada } = entradas[0];
    const ruta =
      porLaCalle(cuadras, entrada.nodo, extremo, calle) ??
      porLaCalle(cuadras, entrada.nodo, extremo, null);
    return ruta && { largo: entrada.largo + ruta.largo, tramos: ruta.tramos, calle, propia: propia(calle) };
  };

  // Sin esquinas la ruta no dobla: los dos puntos comparten calle y se unen
  // por ella.
  if (!esquinas.length) {
    const [a, b] = puntosFila;
    if (!a || !b) return { tramos, usadas };
    const comun = [...callesFila].filter(
      (c) => grafo.nombreDe.get(c)?.toLowerCase() === (a.calle ?? b.calle)?.toLowerCase(),
    );
    for (const calle of comun.length ? comun : [...callesFila]) {
      const ea = entradaALaCalle(cuadras, a, calle);
      const eb = entradaALaCalle(cuadras, b, calle);
      const ruta = ea && eb && (porLaCalle(cuadras, ea.nodo, eb.nodo, calle) ?? porLaCalle(cuadras, ea.nodo, eb.nodo, null));
      if (!ruta) continue;
      tramos.push(...ruta.tramos);
      usadas.add(calle);
      break;
    }
    return { tramos, usadas };
  }

  // Cada punto, como el reclamo o el local, se conecta con el extremo de la
  // ruta al que llega por su propia calle, aunque quede lejos: la ruta con
  // menos giros puede recorrer kilómetros por la calle del local. Sin calle
  // propia, con el extremo más cercano. Una fila puede nombrar más de dos
  // puntos, como dos locales homónimos en la misma calle.
  const extremos = [esquinas[0], esquinas[esquinas.length - 1]];
  for (const punto of puntosFila) {
    const opciones = extremos.map((e) => conectar(punto, e)).filter(Boolean);
    if (!opciones.length) continue;
    const mejor = opciones.reduce((a, b) => (b.propia - a.propia || a.largo - b.largo) > 0 ? b : a);
    tramos.push(...mejor.tramos);
    usadas.add(mejor.calle);
  }
  return { tramos, usadas };
}

/**
 * Cómo mostrar en una tabla una lista o un nodo suelto. Los nodos, como las
 * esquinas de una ruta, se muestran como la cantidad que son.
 */
export function textoDeLista(valor) {
  const lista = Array.isArray(valor) ? valor : [valor];
  if (!lista.length || typeof lista[0] !== "object" || lista[0] === null) return lista.join(", ");
  const esquinas = lista.every((n) => n?.labels?.includes("Interseccion"));
  const n = lista.length;
  return esquinas ? `${n} ${n === 1 ? "esquina" : "esquinas"}` : `${n} ${n === 1 ? "nodo" : "nodos"}`;
}

/**
 * Lo que nombra un resultado: calles por su nombre, y lugares, reclamos y
 * venues por la clave con que los identifica su etiqueta.
 *
 * Una fila que trae las esquinas donde dobla una ruta enciende solo las
 * cuadras que se recorren, en `tramos`, y no las calles enteras. Las calles que
 * la fila nombra y la ruta no recorre, como el origen y el destino de la 06,
 * se encienden enteras.
 */
export function ubicarFilas(grafo, filas, columnasIgnoradas = new Set()) {
  const calles = new Set();
  const puntos = new Map();
  const tramos = new Set();
  const callesEnRuta = new Set();
  let ambiguos = 0;
  for (const fila of filas ?? []) {
    // Los valores de la fila completa, para separar homónimos: si la fila
    // nombra la calle, el lugar que se busca es el de esa calle.
    // Una columna puede traer una lista, como las calles intermedias de una
    // ruta o los nombres que junta un COLLECT, y cada elemento cuenta aparte.
    const enLaFila = new Set(
      Object.entries(fila)
        .filter(([col]) => !columnasIgnoradas.has(col))
        .flatMap(([, v]) => (Array.isArray(v) ? v : [v]))
        .filter((v) => typeof v === "string")
        .map((v) => v.toLowerCase()),
    );
    const callesFila = new Set();
    const callesRuta = new Set();
    const puntosFila = new Map();
    for (const llave of enLaFila) {
      const calle = grafo.porNombre.get(llave);
      if (calle) callesFila.add(calle);
      for (const homonima of grafo.homonimas.get(llave) ?? []) callesRuta.add(homonima);

      const candidatos = grafo.porClave.get(llave) ?? [];
      const elegidos =
        candidatos.length < 2
          ? candidatos
          : candidatos.filter((p) => p.calle && enLaFila.has(p.calle.toLowerCase()));
      // Un nombre compartido que la fila no alcanza a desambiguar se deja
      // apagado: encender los homónimos pone puntos lejos de su calle.
      if (candidatos.length > 1 && !elegidos.length) ambiguos += 1;
      for (const punto of elegidos) puntosFila.set(`${punto.x},${punto.y}`, punto);
    }

    const esquinas = esquinasDe(fila);
    const ruta = esRuta(fila)
      ? rutaDeFila(grafo, esquinas, callesRuta, [...puntosFila.values()])
      : { tramos: [], usadas: new Set() };
    for (const t of ruta.tramos) tramos.add(t);
    for (const calle of ruta.usadas) callesEnRuta.add(calle);
    // Un nombre puede corresponder a varias calles homónimas, y el índice por
    // nombre guarda una sola: si la ruta ya recorrió una calle con ese nombre,
    // la otra no se enciende entera.
    const nombresEnRuta = new Set([...ruta.usadas].map((c) => grafo.nombreDe.get(c)));
    for (const calle of callesFila) {
      if (!ruta.usadas.has(calle) && !nombresEnRuta.has(grafo.nombreDe.get(calle))) calles.add(calle);
    }
    for (const [llave, punto] of puntosFila) puntos.set(llave, punto);
  }
  // Una calle entera ya incluye sus cuadras.
  const sueltos = [...tramos].filter((t) => !calles.has(t.calle));
  const nombradas = new Set([...calles, ...callesEnRuta]).size;
  return { calles, tramos: sueltos, nombradas, puntos: [...puntos.values()], ambiguos };
}

/**
 * Ubica nodos concretos, como los que devuelve el inspector de constantes:
 * las calles por su `calle_id` y el resto por sus coordenadas.
 */
export function ubicarNodos(grafo, nodos) {
  const calles = new Set();
  const puntos = new Map();
  for (const nodo of nodos ?? []) {
    const props = nodo?.props ?? {};
    if (nodo?.labels?.includes("Calle") && props.calle_id) {
      calles.add(props.calle_id);
    } else if (typeof props.lon === "number" && typeof props.lat === "number") {
      const llave = `${props.lon},${props.lat}`;
      puntos.set(llave, grafo.porCoordenada.get(llave) ?? { x: props.lon, y: props.lat });
    }
  }
  return { calles, puntos: [...puntos.values()] };
}

/**
 * Encuentra las constantes de texto de una consulta junto con el nodo al que
 * pertenecen.
 *
 * Los archivos de `consultas/` escriben sus constantes de dos formas, `v.prop = 'x'` y
 * `v.prop IN ['x', 'y']`, y declaran la etiqueta de cada variable en el
 * patrón. Eso alcanza para saber que `'000050'` es el `reporte_id` de un
 * `Reclamo`. El parser sirve para las consultas del repositorio y no pretende
 * cubrir GQL entero: por eso desaparece al editar el texto.
 */
export function constantesDe(gql) {
  const etiquetas = new Map();
  for (const [, variable, etiqueta] of gql.matchAll(/\(\s*([a-z]\w*)\s*:\s*([A-Z]\w*)/g)) {
    etiquetas.set(variable, etiqueta);
  }

  const encontradas = [];
  const anotar = (variable, propiedad, valor, inicio) => {
    const etiqueta = etiquetas.get(variable);
    if (etiqueta) {
      encontradas.push({ etiqueta, propiedad, valor, inicio, fin: inicio + valor.length + 2 });
    }
  };

  for (const m of gql.matchAll(/(\w+)\.(\w+)\s*=\s*'([^']*)'/g)) {
    anotar(m[1], m[2], m[3], m.index + m[0].lastIndexOf("'" + m[3] + "'"));
  }
  for (const m of gql.matchAll(/(\w+)\.(\w+)\s+IN\s*\[([^\]]*)\]/g)) {
    const lista = m[3];
    const desplazamiento = m.index + m[0].indexOf(lista);
    for (const item of lista.matchAll(/'([^']*)'/g)) {
      anotar(m[1], m[2], item[1], desplazamiento + item.index);
    }
  }
  return encontradas.sort((x, y) => x.inicio - y.inicio);
}

/** Etiquetas que la consulta nombra, para saber si el grafo las tiene. */
export function etiquetasDe(gql) {
  return new Set(
    [...gql.matchAll(/[:|]\s*([A-Z][A-Za-z_]*)/g)].map((coincidencia) => coincidencia[1]),
  );
}
