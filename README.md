# MDE de INEGI – plugin de QGIS

Plugin de QGIS para descargar y procesar los Modelos Digitales de Elevación (MDE) LiDAR 1:10,000 de INEGI a partir de las claves de carta.

*QGIS plugin to download and process INEGI (Mexico) 1:10,000 LiDAR elevation models by map sheet key.*

## Requisitos

- QGIS 3.40 o posterior (también QGIS 4.x)
- Conexión a internet
- Una capa de polígonos con el índice de cartas 1:10,000 de INEGI que tenga el campo `cve_carta`
- Solo cubre el territorio de México

## Instalación

**Desde QGIS:** Complementos → Administrar e instalar complementos → buscar "MDE de INEGI" → Instalar.

**Desde un ZIP:** descarga el ZIP de la versión y en QGIS ve a Complementos → Administrar e instalar complementos → Instalar a partir de ZIP.

## Herramientas

Al pulsar el ícono del plugin aparece un menú con dos herramientas.

### 1. Descarga de MDE

1. Carga la capa del índice de cartas y selecciona las cartas que quieres.
2. Elige la capa del índice y el tipo de modelo: **Terreno** o **Superficie**.
3. Pulsa **Descargar**.

Para cada carta, el plugin elige automáticamente la edición más reciente, luego la mejor resolución (1.5 m antes que 5 m) y luego el formato (tif > bil > grid > ascii). Si una descarga falla, prueba la siguiente mejor opción. El resultado es un GeoTIFF comprimido (DEFLATE) llamado `clave_tipo_resolución.tif`. Se conserva el sistema de coordenadas original y las cartas que ya tienen su .tif se omiten.

### 2. Procesar rásteres

Trabaja con rásteres cargados en el proyecto o con una carpeta. Tiene dos procesos opcionales:

- **Limpieza de márgenes:** recorta el borde de cada carta, donde INEGI deja valores inconsistentes. El ancho del margen se elige en cada ejecución.
- **Reproyección:** pasa cada carta a UTM ITRF2008 en la zona que indica su clave (zonas 11 a 16), con la resolución de salida que elijas.

Los archivos originales se reemplazan por los procesados.

## Reportar errores

Usa la pestaña [Issues](../../issues) de este repositorio.

## Licencia

GNU General Public License v2.0 o posterior. Consulta el archivo `LICENSE`.
