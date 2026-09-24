// Mapa de la red vial dibujado sobre canvas, con los datos que entrega el
// propio motor.
//
// La geometría no viene de un archivo aparte ni de un servidor de mapas: sale
// de consultar el grafo. Cada tramo es un par de intersecciones con `lon` y
// `lat`, y el `calle_id` que trae la arista permite encender las calles que
// nombra el resultado de una consulta.
//
// Los tramos se dibujan como rectas entre esquinas. El grafo no guarda la
// geometría intermedia de cada way, así que una curva larga sale como cuerda.
// A escala de comuna el trazado se reconoce igual.

const MODOS = {
  auto: { etiqueta: "Auto", arista: "CONECTA_AUTO" },
  bici: { etiqueta: "Bici", arista: "CONECTA_BICI" },
  peaton: { etiqueta: "Peatón", arista: "CONECTA_PEATON" },
};

// Las tres capas de puntos que cuelgan de la red. La clave es la propiedad por
// la que se reconoce un punto en el resultado de una consulta: los lugares por
// su etiqueta, los reclamos por su identificador, los venues por el suyo.
const CAPAS = {
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

const ZOOM_MAX = 40;
const ZOOM_MIN = 0.8;
const RADIO_PUNTO = 1.7;

/** Lee los tramos de un modo y los deja como arreglo plano de coordenadas. */
function tramosDe(conexion, arista) {
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
function puntosDe(conexion, nombre, capa) {
  const puntos = conexion.execute(capa.consulta, 0);
  for (const p of puntos) p.capa = nombre;
  if (!capa.conCalle) return puntos;

  const calles = new Map();
  for (const f of conexion.execute(capa.conCalle, 0)) calles.set(f.ref, f.calle);
  for (const p of puntos) p.calle = calles.get(p.ref);
  return puntos;
}

export function crearMapa(canvas, conexion, colores, alTocar) {
  const redes = {};
  for (const [nombre, modo] of Object.entries(MODOS)) {
    redes[nombre] = tramosDe(conexion, modo.arista);
  }

  const capas = {};
  const visibles = new Set();
  // Para volver de una coordenada al punto que la ocupa, al tocar el mapa.
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
  for (const c of conexion.execute("MATCH (c:Calle) RETURN c.calle_id AS id, c.nombre AS nombre", 0)) {
    porNombre.set(c.nombre.toLowerCase(), c.id);
  }

  const todos = Object.values(redes).flat();
  const limites = todos.reduce(
    (l, t) => ({
      xmin: Math.min(l.xmin, t.x1, t.x2),
      xmax: Math.max(l.xmax, t.x1, t.x2),
      ymin: Math.min(l.ymin, t.y1, t.y2),
      ymax: Math.max(l.ymax, t.y1, t.y2),
    }),
    { xmin: Infinity, xmax: -Infinity, ymin: Infinity, ymax: -Infinity },
  );

  let modo = "auto";
  let destacadas = new Set();
  let puntosDestacados = [];
  let zoom = 1;
  let centro = { x: (limites.xmin + limites.xmax) / 2, y: (limites.ymin + limites.ymax) / 2 };
  let base = 1;
  let ancho = 0;
  let alto = 0;

  function medir() {
    const caja = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    ancho = caja.width;
    alto = caja.height;
    canvas.width = Math.round(ancho * dpr);
    canvas.height = Math.round(alto * dpr);
    // La longitud se comprime con el coseno de la latitud, si no la comuna sale
    // estirada a lo ancho.
    const cos = Math.cos((centro.y * Math.PI) / 180);
    const anchoGrados = (limites.xmax - limites.xmin) * cos;
    const altoGrados = limites.ymax - limites.ymin;
    base = Math.min(ancho / anchoGrados, alto / altoGrados) * 0.94;
    canvas.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const proyectar = (x, y) => {
    const cos = Math.cos((centro.y * Math.PI) / 180);
    const escala = base * zoom;
    return [
      ancho / 2 + (x - centro.x) * cos * escala,
      alto / 2 - (y - centro.y) * escala,
    ];
  };

  function dibujar() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, ancho, alto);

    const tramos = redes[modo];
    const grosor = Math.min(2.2, 0.55 + zoom * 0.25);

    ctx.lineCap = "round";
    ctx.strokeStyle = colores.red;
    ctx.lineWidth = grosor;
    ctx.beginPath();
    for (const t of tramos) {
      if (destacadas.size && destacadas.has(t.calle)) continue;
      const [ax, ay] = proyectar(t.x1, t.y1);
      const [bx, by] = proyectar(t.x2, t.y2);
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
    }
    ctx.stroke();

    if (destacadas.size) {
      ctx.strokeStyle = colores.destacado;
      ctx.lineWidth = grosor + 1.6;
      ctx.beginPath();
      for (const t of tramos) {
        if (!destacadas.has(t.calle)) continue;
        const [ax, ay] = proyectar(t.x1, t.y1);
        const [bx, by] = proyectar(t.x2, t.y2);
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
      }
      ctx.stroke();
    }

    const radio = Math.min(4.5, RADIO_PUNTO + zoom * 0.35);
    for (const nombre of visibles) {
      ctx.fillStyle = colores[CAPAS[nombre].color];
      ctx.beginPath();
      for (const p of capas[nombre]) {
        const [x, y] = proyectar(p.x, p.y);
        if (x < -radio || y < -radio || x > ancho + radio || y > alto + radio) continue;
        ctx.moveTo(x + radio, y);
        ctx.arc(x, y, radio, 0, Math.PI * 2);
      }
      ctx.fill();
    }

    if (puntosDestacados.length) {
      ctx.fillStyle = colores.destacado;
      ctx.strokeStyle = colores.papel;
      ctx.lineWidth = 1.5;
      for (const p of puntosDestacados) {
        const [x, y] = proyectar(p.x, p.y);
        ctx.beginPath();
        ctx.arc(x, y, radio + 2.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }
  }

  function redibujar() {
    medir();
    dibujar();
  }

  // --- Navegación: arrastrar con uno o dos dedos, pellizcar para acercar ---
  const punteros = new Map();
  let pellizco = null;

  // Un toque es un puntero que se levanta cerca de donde bajó. Más lejos que
  // esto ya fue un arrastre del mapa.
  const TOLERANCIA_TOQUE = 6;
  // Radio en pantalla para decidir qué punto se tocó.
  const RADIO_TOQUE = 14;
  let partida = null;

  canvas.addEventListener("pointerdown", (e) => {
    // La captura falla si el puntero ya se soltó, y no es motivo para cortar.
    try {
      canvas.setPointerCapture(e.pointerId);
    } catch (error) {
      /* sin captura: el arrastre igual funciona mientras el puntero esté encima */
    }
    punteros.set(e.pointerId, { x: e.clientX, y: e.clientY });
    partida = punteros.size === 1 ? { x: e.clientX, y: e.clientY } : null;
    pellizco = null;
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!punteros.has(e.pointerId)) return;
    const previo = punteros.get(e.pointerId);
    punteros.set(e.pointerId, { x: e.clientX, y: e.clientY });

    const cos = Math.cos((centro.y * Math.PI) / 180);
    const escala = base * zoom;

    if (punteros.size === 1) {
      centro = {
        x: centro.x - (e.clientX - previo.x) / (cos * escala),
        y: centro.y + (e.clientY - previo.y) / escala,
      };
    } else if (punteros.size === 2) {
      const [a, b] = [...punteros.values()];
      const distancia = Math.hypot(a.x - b.x, a.y - b.y);
      if (pellizco) zoom = limitar(zoom * (distancia / pellizco));
      pellizco = distancia;
    }
    dibujar();
  });

  /** El punto dibujado más cercano a un lugar de la pantalla. */
  function puntoEn(clienteX, clienteY) {
    const caja = canvas.getBoundingClientRect();
    const px = clienteX - caja.left;
    const py = clienteY - caja.top;

    const candidatos = [];
    for (const nombre of visibles) candidatos.push(...capas[nombre]);
    // Los destacados se dibujan aunque su capa esté apagada.
    for (const d of puntosDestacados) {
      const punto = porCoordenada.get(`${d.x},${d.y}`);
      if (punto) candidatos.push(punto);
    }

    let cerca = null;
    let menor = RADIO_TOQUE;
    for (const punto of candidatos) {
      const [x, y] = proyectar(punto.x, punto.y);
      const distancia = Math.hypot(x - px, y - py);
      if (distancia < menor) {
        menor = distancia;
        cerca = { punto, x, y };
      }
    }
    return cerca;
  }

  const soltar = (e) => {
    const era = partida;
    punteros.delete(e.pointerId);
    if (punteros.size < 2) pellizco = null;
    if (punteros.size || !era || !alTocar) return;
    if (Math.hypot(e.clientX - era.x, e.clientY - era.y) > TOLERANCIA_TOQUE) return;
    alTocar(puntoEn(e.clientX, e.clientY));
  };
  canvas.addEventListener("pointerup", soltar);
  canvas.addEventListener("pointercancel", soltar);

  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      zoom = limitar(zoom * Math.exp(-e.deltaY / 400));
      dibujar();
    },
    { passive: false },
  );

  const limitar = (z) => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));

  window.addEventListener("resize", redibujar);
  redibujar();

  return {
    modos: MODOS,
    /** Vuelve a pintar con los colores actuales, al cambiar el tema. */
    redibujar: dibujar,
    tramos: (nombre) => redes[nombre].length,
    verModo(nombre) {
      modo = nombre;
      dibujar();
    },
    capas: CAPAS,
    puntos: (nombre) => capas[nombre].length,
    verCapa(nombre, visible) {
      if (visible) visibles.add(nombre);
      else visibles.delete(nombre);
      dibujar();
    },
    /**
     * Enciende lo que el resultado nombre: calles por su nombre, y lugares,
     * reclamos y venues por la clave con que los identifica su etiqueta.
     */
    destacar(filas, columnasIgnoradas = new Set()) {
      destacadas = new Set();
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
          const calle = porNombre.get(llave);
          if (calle) destacadas.add(calle);

          const candidatos = porClave.get(llave) ?? [];
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
      puntosDestacados = [...puntos.values()];
      dibujar();
      return { calles: destacadas.size, puntos: puntosDestacados.length, ambiguos };
    },
    /**
     * Enciende nodos concretos, como los que devuelve el inspector de
     * constantes: las calles por su `calle_id` y el resto por sus coordenadas.
     */
    destacarNodos(nodos) {
      destacadas = new Set();
      const puntos = new Map();
      for (const nodo of nodos ?? []) {
        const props = nodo?.props ?? {};
        if (nodo?.labels?.includes("Calle") && props.calle_id) {
          destacadas.add(props.calle_id);
        } else if (typeof props.lon === "number" && typeof props.lat === "number") {
          puntos.set(`${props.lon},${props.lat}`, { x: props.lon, y: props.lat });
        }
      }
      puntosDestacados = [...puntos.values()];
      dibujar();
      return { calles: destacadas.size, puntos: puntosDestacados.length };
    },
    limpiar() {
      destacadas = new Set();
      puntosDestacados = [];
      dibujar();
    },
    reiniciar() {
      zoom = 1;
      centro = { x: (limites.xmin + limites.xmax) / 2, y: (limites.ymin + limites.ymax) / 2 };
      redibujar();
    },
  };
}
