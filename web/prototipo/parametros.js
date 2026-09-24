// Parámetros de una consulta: las constantes que se pueden cambiar sin editar
// el texto.
//
// Los doce archivos escriben sus constantes de dos formas, `v.prop = 'x'` y
// `v.prop IN ['x', 'y']`, y declaran la etiqueta de cada variable en el
// patrón. Con eso cada constante se vuelve un parámetro con etiqueta y
// propiedad, y sus valores posibles salen del grafo. El `LIMIT` también es un
// parámetro. El parser sirve para las consultas del repositorio y no pretende
// cubrir GQL entero.

/** Los parámetros de una consulta, en el orden en que aparecen. */
export function parametrosDe(gql) {
  const etiquetas = new Map();
  for (const [, variable, etiqueta] of gql.matchAll(/\(\s*([a-z]\w*)\s*:\s*([A-Z]\w*)/g)) {
    etiquetas.set(variable, etiqueta);
  }
  const parametros = [];
  for (const m of gql.matchAll(/(\w+)\.(\w+)\s*=\s*'([^']*)'/g)) {
    const etiqueta = etiquetas.get(m[1]);
    if (!etiqueta) continue;
    const inicio = m.index + m[0].lastIndexOf(`'${m[3]}'`);
    parametros.push({ tipo: "igual", etiqueta, propiedad: m[2], original: m[3], inicio, fin: inicio + m[3].length + 2 });
  }
  for (const m of gql.matchAll(/(\w+)\.(\w+)\s+IN\s*(\[[^\]]*\])/g)) {
    const etiqueta = etiquetas.get(m[1]);
    if (!etiqueta) continue;
    const inicio = m.index + m[0].lastIndexOf(m[3]);
    const original = [...m[3].matchAll(/'([^']*)'/g)].map((item) => item[1]);
    parametros.push({ tipo: "lista", etiqueta, propiedad: m[2], original, inicio, fin: inicio + m[3].length });
  }
  for (const m of gql.matchAll(/\bLIMIT\s+(\d+)/g)) {
    parametros.push({ tipo: "limite", original: Number(m[1]), inicio: m.index, fin: m.index + m[0].length });
  }
  return parametros.sort((a, b) => a.inicio - b.inicio);
}

/** El texto de un valor tal como va en la consulta. */
function literal(parametro, valor) {
  if (parametro.tipo === "igual") return `'${valor}'`;
  if (parametro.tipo === "lista") return `[${valor.map((v) => `'${v}'`).join(", ")}]`;
  return valor ? `LIMIT ${valor}` : "";
}

/**
 * La consulta en tramos: texto fijo y texto de cada parámetro con su valor
 * actual. Sirve para escribirla y para mostrarla con los parámetros marcados.
 */
export function tramosDe(gql, parametros, valores) {
  const tramos = [];
  let cursor = 0;
  parametros.forEach((parametro, i) => {
    tramos.push({ texto: gql.slice(cursor, parametro.inicio) });
    tramos.push({ texto: literal(parametro, valores[i]), indice: i });
    cursor = parametro.fin;
  });
  tramos.push({ texto: gql.slice(cursor) });
  return tramos;
}

export const escribir = (gql, parametros, valores) =>
  tramosDe(gql, parametros, valores).map((t) => t.texto).join("");

/**
 * Los valores que toma una propiedad en el grafo, del más frecuente al menos.
 * Se descartan los que traen una comilla, que cortarían el literal.
 */
export function valoresDe(correr, etiqueta, propiedad) {
  const resultado = correr(
    `MATCH (n:${etiqueta}) RETURN n.${propiedad} AS valor, COUNT(n) AS nodos ` +
      `GROUP BY n.${propiedad} ORDER BY nodos DESC`,
  );
  return (resultado.filas ?? []).filter(
    (f) => typeof f.valor === "string" && f.valor && !f.valor.includes("'"),
  );
}
