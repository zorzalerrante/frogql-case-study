// Entintado del mapa base. Los tonos del HUD se llevan al estilo de MapLibre al
// cargarlo, aplicando a cada color literal de las propiedades de pintura las
// mismas matrices con que la especificación de CSS define sepia(), hue-rotate(),
// saturate() y brightness(). El resultado es el del filtro CSS equivalente,
// pero calculado una sola vez y no en cada cuadro.

export const ESTILOS = {
  oscuro: 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
  claro: 'https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json',
};
// Equivalentes a `sepia(0.35) hue-rotate(215deg) saturate(1.25) brightness(0.92)` y
// `sepia(0.22) hue-rotate(250deg) saturate(1.05)`.
const TINTES = {
  oscuro: [['sepia', 0.35], ['hue-rotate', 215], ['saturate', 1.25], ['brightness', 0.92]],
  claro: [['sepia', 0.22], ['hue-rotate', 250], ['saturate', 1.05]],
};

// Matrices 3x3 (filas) de la especificacion Filter Effects, sobre sRGB en [0, 1].
const MATRICES = {
  sepia: s => { const a = 1 - s; return [
    [0.393 + 0.607 * a, 0.769 - 0.769 * a, 0.189 - 0.189 * a],
    [0.349 - 0.349 * a, 0.686 + 0.314 * a, 0.168 - 0.168 * a],
    [0.272 - 0.272 * a, 0.534 - 0.534 * a, 0.131 + 0.869 * a]]; },
  saturate: s => [
    [0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s],
    [0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s],
    [0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s]],
  'hue-rotate': grados => { const c = Math.cos((grados * Math.PI) / 180), s = Math.sin((grados * Math.PI) / 180); return [
    [0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928],
    [0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283],
    [0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072]]; },
  brightness: b => [[b, 0, 0], [0, b, 0], [0, 0, b]],
};

// Aplica los filtros en orden, con recorte a [0, 1] entre uno y otro, como hace el navegador.
function filtrar(rgb, filtros) {
  let v = rgb;
  for (const [nombre, valor] of filtros) {
    const m = MATRICES[nombre](valor);
    v = m.map(fila => Math.min(1, Math.max(0, fila[0] * v[0] + fila[1] * v[1] + fila[2] * v[2])));
  }
  return v;
}

// El contexto 2D normaliza cualquier color CSS a `#rrggbb` o `rgba(r, g, b, a)`.
const ctx2d = document.createElement('canvas').getContext('2d');
function leerColor(texto) {
  ctx2d.fillStyle = '#010203';
  ctx2d.fillStyle = texto;
  const n = ctx2d.fillStyle;
  if (n === '#010203' && !/^#010203$/i.test(texto)) return null;
  if (n.startsWith('#')) return [parseInt(n.slice(1, 3), 16) / 255, parseInt(n.slice(3, 5), 16) / 255, parseInt(n.slice(5, 7), 16) / 255, 1];
  const m = n.match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const p = m[1].split(',').map(Number);
  return [p[0] / 255, p[1] / 255, p[2] / 255, p.length > 3 ? p[3] : 1];
}

function tintarColor(texto, filtros) {
  const c = leerColor(texto);
  if (!c) return texto;
  const [r, g, b] = filtrar(c.slice(0, 3), filtros).map(x => Math.round(x * 255));
  return `rgba(${r}, ${g}, ${b}, ${c[3]})`;
}

// Recorre un valor de pintura (color literal o expresion) y entinta los colores
// explicitos (#, rgb, hsl). Los nombres de color en ingles no se tocan, porque
// en las expresiones podrian ser valores de atributos ("snow", "wood").
function tintarValor(v, filtros) {
  if (typeof v === 'string') return /^(#|rgb|hsl)/i.test(v) ? tintarColor(v, filtros) : v;
  if (Array.isArray(v)) return v.map((x, i) => (i === 0 && typeof x === 'string' ? x : tintarValor(x, filtros)));
  if (v && typeof v === 'object' && Array.isArray(v.stops)) return { ...v, stops: v.stops.map(([z, c]) => [z, tintarValor(c, filtros)]) };
  return v;
}

export function tintarEstilo(estilo, filtros) {
  const capas = estilo.layers.map(capa => {
    if (!capa.paint) return capa;
    const paint = {};
    for (const [k, v] of Object.entries(capa.paint)) paint[k] = k.endsWith('-color') ? tintarValor(v, filtros) : v;
    return { ...capa, paint };
  });
  return { ...estilo, layers: capas };
}

const cache = new Map();
// Estilo de CARTO ya entintado para el tema; se descarga una vez por tema.
export function estiloEntintado(tema) {
  if (!cache.has(tema)) cache.set(tema, fetch(ESTILOS[tema]).then(r => r.json()).then(s => tintarEstilo(s, TINTES[tema])));
  return cache.get(tema);
}
