"""Reglas de acceso por modo de transporte sobre los tags de OpenStreetMap.

Un mismo conjunto de ways produce redes distintas según quien circule. La
autopista central admite autos y prohibe peatones; un paseo peatonal admite
personas caminando y no autos; un pasaje interior con `access=private` no
pertenece a ninguna red pública. Cada perfil describe esas reglas de forma
declarativa para que la red por modo sea un filtro sobre los mismos segmentos
y no una descarga distinta.

Orden de evaluación, para cada segmento y cada modo:

1. Si `highway` está en `prohibido`, el modo no circula, sin excepciones.
2. Si el tag propio del modo (`motor_vehicle`, `bicycle`, `foot`) niega el
   paso, el modo no circula.
3. Si el tag propio del modo lo permite de forma explicita, circula aunque
   `highway` no este en la lista del perfil.
4. Si `access` niega el paso y el tag propio no lo habilita, no circula.
5. En otro caso, circula si `highway` está en la lista del perfil.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

ENLACES = frozenset(
    {
        "motorway_link",
        "trunk_link",
        "primary_link",
        "secondary_link",
        "tertiary_link",
    }
)

# Vías por las que circulan vehículos motorizados.
VEHICULAR = (
    frozenset(
        {
            "motorway",
            "trunk",
            "primary",
            "secondary",
            "tertiary",
            "unclassified",
            "residential",
            "living_street",
            "service",
        }
    )
    | ENLACES
)

# Vías de acceso controlado, donde no se camina ni se pedalea.
ACCESO_CONTROLADO = frozenset({"motorway", "trunk", "motorway_link", "trunk_link"})

# Vías reservadas a la circulación a pie.
PEATONAL = frozenset({"footway", "path", "pedestrian", "steps", "corridor", "track"})

# Vías reservadas a la bicicleta.
CICLISTA = frozenset({"cycleway"})

# Valores de un tag de acceso que habilitan o niegan el paso.
PERMITE = frozenset({"yes", "designated", "permissive", "destination", "official"})
NIEGA = frozenset({"no", "private"})

# Valores de `service` que describen circulación interna de un recinto
# (pasillos de estacionamiento, accesos a garaje). No son calles.
SERVICIO_INTERNO = frozenset({"parking_aisle", "driveway"})


@dataclass(frozen=True)
class Perfil:
    """Reglas de un modo de transporte.

    Atributos
    ---------
    nombre : identificador corto, usado en nombres de archivo.
    etiqueta : label de la arista en el grafo de propiedades.
    descripción : una línea para los reportes.
    highway : valores de `highway` que el modo usa por defecto.
    prohibido : valores de `highway` que el modo nunca usa.
    llaves : tags de acceso propios del modo, del más específico al más
        general. El primero que traiga valor decide.
    dirigido : si el modo respeta el sentido de circulación (`oneway`).
    """

    nombre: str
    etiqueta: str
    descripcion: str
    highway: frozenset[str]
    prohibido: frozenset[str] = field(default_factory=frozenset)
    llaves: tuple[str, ...] = ()
    dirigido: bool = False


PERFILES = {
    "auto": Perfil(
        nombre="auto",
        etiqueta="CONECTA_AUTO",
        descripcion="Vehículos motorizados particulares",
        highway=VEHICULAR,
        prohibido=PEATONAL | CICLISTA,
        llaves=("motorcar", "motor_vehicle", "vehicle"),
        dirigido=True,
    ),
    "bici": Perfil(
        nombre="bici",
        etiqueta="CONECTA_BICI",
        descripcion="Bicicletas",
        highway=(VEHICULAR - ACCESO_CONTROLADO) | CICLISTA | {"path", "track"},
        prohibido=ACCESO_CONTROLADO | {"steps", "corridor"},
        llaves=("bicycle", "vehicle"),
        dirigido=False,
    ),
    "peaton": Perfil(
        nombre="peaton",
        etiqueta="CONECTA_PEATON",
        descripcion="Circulación a pie",
        highway=(VEHICULAR - ACCESO_CONTROLADO) | PEATONAL,
        prohibido=ACCESO_CONTROLADO | CICLISTA,
        llaves=("foot",),
        dirigido=False,
    ),
}


def _columna(vias: pd.DataFrame, nombre: str) -> pd.Series:
    """Columna de tags como texto en minúsculas, vacía si el tag no existe."""
    if nombre not in vias.columns:
        return pd.Series("", index=vias.index, dtype="object")
    return vias[nombre].fillna("").astype(str).str.strip().str.lower()


def _acceso_del_modo(vias: pd.DataFrame, llaves: tuple[str, ...]) -> pd.Series:
    """Primer valor no vacío entre los tags de acceso del modo."""
    valor = pd.Series("", index=vias.index, dtype="object")
    for llave in llaves:
        columna = _columna(vias, llave)
        valor = valor.where(valor != "", columna)
    return valor


def permite(vias: pd.DataFrame, perfil: Perfil) -> pd.Series:
    """Marca que segmentos admiten la circulación del modo."""
    highway = _columna(vias, "highway")
    acceso_general = _columna(vias, "access")
    acceso_modo = _acceso_del_modo(vias, perfil.llaves)
    servicio = _columna(vias, "service")

    por_clase = highway.isin(perfil.highway)
    prohibida = highway.isin(perfil.prohibido)
    habilita = acceso_modo.isin(PERMITE)
    bloquea = acceso_modo.isin(NIEGA) | (
        acceso_general.isin(NIEGA) & ~habilita
    )
    interno = servicio.isin(SERVICIO_INTERNO)

    return (por_clase | habilita) & ~prohibida & ~bloquea & ~interno


def permisos(vias: pd.DataFrame) -> pd.DataFrame:
    """Una columna booleana por modo, con el mismo índice que `vias`."""
    return pd.DataFrame(
        {f"permite_{nombre}": permite(vias, perfil) for nombre, perfil in PERFILES.items()},
        index=vias.index,
    )


def sentido(vias: pd.DataFrame) -> pd.Series:
    """Traduce el tag `oneway` a `ambos`, `directo` o `inverso`.

    `directo` es el sentido en que están ordenados los vertices de la way;
    `inverso` corresponde a `oneway=-1`, que OSM usa cuando el sentido de
    circulación va contra el orden de digitalización.
    """
    valor = _columna(vias, "oneway")
    resultado = pd.Series("ambos", index=vias.index, dtype="object")
    resultado[valor.isin({"yes", "true", "1"})] = "directo"
    resultado[valor.isin({"-1", "reverse"})] = "inverso"
    return resultado


def tiene_ciclovia(vias: pd.DataFrame) -> pd.Series:
    """Marca segmentos con infraestructura ciclista declarada en los tags.

    Una ciclovía aparece en OSM de dos formas: como way propia
    (`highway=cycleway`) o como atributo de la calle que la contiene
    (`cycleway:left=track`). Contar solo la primera subestima la red.
    """
    es_via_propia = _columna(vias, "highway") == "cycleway"
    con_atributo = pd.Series(False, index=vias.index)
    for llave in ("cycleway", "cycleway:left", "cycleway:right"):
        valor = _columna(vias, llave)
        con_atributo |= (valor != "") & ~valor.isin({"no", "separate", "none"})
    return es_via_propia | con_atributo
