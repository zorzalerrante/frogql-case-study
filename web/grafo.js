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
      "n.categoria AS titulo, n.fecha AS fecha, n.descripcion AS texto",
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
  for (const c of conexion.execute("MATCH (c:Calle) RETURN c.calle_id AS id, c.nombre AS nombre", 0)) {
    porNombre.set(c.nombre.toLowerCase(), c.id);
    nombreDe.set(c.id, c.nombre);
  }

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

  return { redes, capas, porCoordenada, porClave, porNombre, nombreDe, limites };
}

/**
 * Lo que nombra un resultado: calles por su nombre, y lugares, reclamos y
 * venues por la clave con que los identifica su etiqueta.
 */
export function ubicarFilas(grafo, filas, columnasIgnoradas = new Set()) {
  const calles = new Set();
  const puntos = new Map();
  let ambiguos = 0;
  for (const fila of filas ?? []) {
    // Los valores de la fila completa, para separar homónimos: si la fila
    // nombra la calle, el lugar que se busca es el de esa calle.
    const enLaFila = new Set(
      Object.entries(fila)
        .filter(([col, v]) => typeof v === "string" && !columnasIgnoradas.has(col))
        .map(([, v]) => v.toLowerCase()),
    );
    for (const llave of enLaFila) {
      const calle = grafo.porNombre.get(llave);
      if (calle) calles.add(calle);

      const candidatos = grafo.porClave.get(llave) ?? [];
      const elegidos =
        candidatos.length < 2
          ? candidatos
          : candidatos.filter((p) => p.calle && enLaFila.has(p.calle.toLowerCase()));
      // Un nombre compartido que la fila no alcanza a desambiguar se deja
      // apagado: encender los homónimos pone puntos lejos de su calle.
      if (candidatos.length > 1 && !elegidos.length) ambiguos += 1;
      for (const punto of elegidos) puntos.set(`${punto.x},${punto.y}`, punto);
    }
  }
  return { calles, puntos: [...puntos.values()], ambiguos };
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
