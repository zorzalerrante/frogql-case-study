"""Componentes para construir redes viales de OpenStreetMap y exportarlas
como grafo de propiedades.

El paquete separa las responsabilidades así:

- `areas`: las áreas de estudio, de la comuna a la ciudad.
- `config`: rutas, selección del área activa y resolución de fuentes.
- `descarga`: extracción de OpenStreetMap con quackosm.
- `perfiles`: reglas de acceso por modo de transporte (auto, bicicleta, pie).
- `grafo`, `calles`: construcción de la topología y agregación de segmentos
  en calles con nombre.
- `contexto`: capas no viales (reportes SOSAFE, zonas censales, venues).
- `propiedades`, `exportar`: armado y serialización del grafo de propiedades.
"""
