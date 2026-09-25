// Mapa de la red vial dibujado sobre canvas, con los datos que entrega el
// propio motor. La lectura del grafo vive en `grafo.js`; acá solo se dibuja.
import { MODOS, CAPAS, leerGrafo, ubicarFilas, ubicarNodos } from "./grafo.js";

const ZOOM_MAX = 40;
const ZOOM_MIN = 0.8;
const RADIO_PUNTO = 1.7;

export function crearMapa(canvas, conexion, colores, alTocar) {
  const grafo = leerGrafo(conexion);
  const { redes, capas, porCoordenada, limites } = grafo;
  const visibles = new Set();

  let modo = "auto";
  let destacadas = new Set();
  // Las cuadras de una ruta, que se encienden sin encender su calle entera.
  let cuadrasDestacadas = [];
  // La ruta elegida entre varias. Con una elegida, las demás se atenúan.
  let cuadrasElegidas = [];
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

    // Una ruta se dibuja con las cuadras de cualquier modo, porque la consulta
    // la arma sobre las calles y no sobre la red que se está mirando.
    const trazar = (tramosRuta, ancho, alfa) => {
      if (!tramosRuta.length) return;
      ctx.globalAlpha = alfa;
      ctx.strokeStyle = colores.destacado;
      ctx.lineWidth = ancho;
      ctx.beginPath();
      for (const t of tramosRuta) {
        const [ax, ay] = proyectar(t.x1, t.y1);
        const [bx, by] = proyectar(t.x2, t.y2);
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    };
    trazar(cuadrasDestacadas, grosor + 1.6, cuadrasElegidas.length ? 0.35 : 1);
    trazar(cuadrasElegidas, grosor + 3, 1);

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
      const ubicado = ubicarFilas(grafo, filas, columnasIgnoradas);
      destacadas = ubicado.calles;
      cuadrasDestacadas = ubicado.tramos;
      cuadrasElegidas = [];
      puntosDestacados = ubicado.puntos;
      dibujar();
      return { calles: ubicado.nombradas, puntos: puntosDestacados.length, ambiguos: ubicado.ambiguos };
    },
    /** Resalta una de las rutas del resultado sobre las demás, o ninguna. */
    elegirRuta(fila, columnasIgnoradas = new Set()) {
      cuadrasElegidas = fila ? ubicarFilas(grafo, [fila], columnasIgnoradas).tramos : [];
      dibujar();
    },
    /** Enciende nodos concretos, como los que devuelve el inspector de constantes. */
    destacarNodos(nodos) {
      const ubicado = ubicarNodos(grafo, nodos);
      destacadas = ubicado.calles;
      cuadrasDestacadas = [];
      cuadrasElegidas = [];
      puntosDestacados = ubicado.puntos;
      dibujar();
      return { calles: destacadas.size, puntos: puntosDestacados.length };
    },
    limpiar() {
      destacadas = new Set();
      cuadrasDestacadas = [];
      cuadrasElegidas = [];
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
