"""Áreas de estudio del caso, de la comuna a la ciudad.

El mismo pipeline corre sobre dos escalas. Independencia es una comuna de 7
km^2 y sirve para entender el modelo leyendo los datos a ojo. El Gran Santiago
son 34 comunas y sirve para medir cómo escala el grafo y cuánto tarda froGQL
en cargarlo y consultarlo.

Un área se define por la lista de comunas que la componen. El límite sale de
las relaciones `boundary=administrative` con `admin_level=8` de OpenStreetMap,
que es el nivel de las comunas chilenas, así que las dos escalas usan la misma
fuente y el mismo criterio. El `bbox` solo acota la búsqueda de esas
relaciones; el recorte final usa el polígono.

Un área puede además declarar un `recorte`, un rectángulo que acota el polígono
resultante. El Gran Santiago lo necesita: varias de sus comunas se extienden
mucho más allá del área urbana continua, y Lo Barnechea llega hasta la frontera
con Argentina. Sin recorte el área pasa de 1145 a 2270 km^2, casi el doble,
mientras la red solo crece 5%, porque lo que se agrega es cordillera.
"""

from __future__ import annotations

from dataclasses import dataclass

# Las 32 comunas de la Provincia de Santiago más Puente Alto y San Bernardo,
# que es la definición habitual del Gran Santiago como área urbana continua.
COMUNAS_GRAN_SANTIAGO = (
    "Cerrillos",
    "Cerro Navia",
    "Conchalí",
    "El Bosque",
    "Estación Central",
    "Huechuraba",
    "Independencia",
    "La Cisterna",
    "La Florida",
    "La Granja",
    "La Pintana",
    "La Reina",
    "Las Condes",
    "Lo Barnechea",
    "Lo Espejo",
    "Lo Prado",
    "Macul",
    "Maipú",
    "Ñuñoa",
    "Pedro Aguirre Cerda",
    "Peñalolén",
    "Providencia",
    "Pudahuel",
    "Puente Alto",
    "Quilicura",
    "Quinta Normal",
    "Recoleta",
    "Renca",
    "San Bernardo",
    "San Joaquín",
    "San Miguel",
    "San Ramón",
    "Santiago",
    "Vitacura",
)


# Rectángulo del Gran Santiago que usa el curso de datos geográficos para todos
# sus datasets urbanos (`gdsutils.ndvi.BBOX_SANTIAGO`, aplicado en la
# preparación de SOSAFE, eBird, luminosidad y las redes viales). Repetirlo acá
# mantiene este caso de estudio comparable con esos materiales: los reportes
# SOSAFE, por ejemplo, ya vienen recortados a este rectángulo desde el origen.
BBOX_GRAN_SANTIAGO = (-70.85, -33.65, -70.45, -33.30)


@dataclass(frozen=True)
class Area:
    """Parámetros de un área de estudio.

    Atributos
    ---------
    nombre : identificador corto, usado en rutas y nombres de archivo.
    titulo : nombre legible para los reportes y los títulos de figuras.
    comunas : comunas que componen el área, tal como las nombra OSM.
    bbox : rectángulo de búsqueda de los límites administrativos, en grados.
    recorte : rectángulo que acota el polígono del área, en grados. `None` deja
        las comunas enteras.
    tolerancia_nodo_m : distancia bajo la cual dos coordenadas son el mismo
        nodo del grafo.
    distancia_calle_m : radio máximo para asignar un punto a una calle.
    distancia_cercania_m : radio de las aristas CERCA_DE.
    figuras : si el script de análisis dibuja los mapas. A escala de ciudad
        las figuras de calles tardan más que el resto del pipeline y aportan
        poco, porque el detalle no se distingue.
    """

    nombre: str
    titulo: str
    comunas: tuple[str, ...]
    bbox: tuple[float, float, float, float]
    recorte: tuple[float, float, float, float] | None = None
    tolerancia_nodo_m: float = 1.5
    distancia_calle_m: float = 40.0
    distancia_cercania_m: float = 50.0
    figuras: bool = True


AREAS = {
    "independencia": Area(
        nombre="independencia",
        titulo="Independencia",
        comunas=("Independencia",),
        bbox=(-70.6900, -33.4360, -70.6440, -33.3950),
    ),
    "santiago": Area(
        nombre="santiago",
        titulo="Gran Santiago",
        comunas=COMUNAS_GRAN_SANTIAGO,
        # El rectángulo de búsqueda solo tiene que tocar cada relación comunal
        # para que quackosm la devuelva entera.
        bbox=(-70.90, -33.70, -70.42, -33.25),
        recorte=BBOX_GRAN_SANTIAGO,
        figuras=False,
    ),
}

PREDETERMINADA = "independencia"
