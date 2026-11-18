# -*- coding: utf-8 -*-
import csv
import os
import shutil
import urllib.error
import urllib.request
import zipfile

from osgeo import gdal

from .compresion import opciones_creacion

PRIORIDAD_RESOLUCION = ["1.5", "5"]
PRIORIDAD_FORMATO = ["tif", "bil", "grid", "ascii"]
SUFIJOS = {"ascii": "as", "bil": "b", "grid": "gr", "tif": "t"}
BASE_ENLACE = "https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/geografia/imagen_cartografica/1_10_000/lidar/"
# Abridor de enlaces que solo acepta https (no abre archivos locales ni otros esquemas)
ABRIDOR = urllib.request.OpenerDirector()
for manejador in (urllib.request.ProxyHandler(),
                  urllib.request.HTTPSHandler(),
                  urllib.request.HTTPRedirectHandler(),
                  urllib.request.HTTPDefaultErrorHandler(),
                  urllib.request.HTTPErrorProcessor(),
                  urllib.request.UnknownHandler()):
    ABRIDOR.add_handler(manejador)

def armar_enlace(fila, formato):
    carpeta = fila["carpeta"].strip().strip("/")
    if carpeta != "":
        carpeta = carpeta + "/"
    return BASE_ENLACE + carpeta + fila["upc"].strip() + "_" + SUFIJOS[formato] + ".zip"

def leer_tabla(ruta_csv):
    tabla = {}
    with open(ruta_csv, newline="", encoding="utf-8-sig") as archivo:
        for fila in csv.DictReader(archivo):
            clave = fila["clvcarta"].strip().upper()
            if clave not in tabla:
                tabla[clave] = []
            tabla[clave].append(fila)
    return tabla


def edicion_de(fila):
    return fila["edicion"].strip()


def opciones_en_orden(tabla, clave, tipo):
    """Todas las opciones de descarga de una carta, de la mejor a la peor."""
    filas = tabla.get(clave.strip().upper(), [])

    del_tipo = []
    for fila in filas:
        if fila["Tipo"].strip() == tipo:
            del_tipo.append(fila)

    ediciones = []
    for fila in del_tipo:
        una_edicion = edicion_de(fila)
        if una_edicion not in ediciones:
            ediciones.append(una_edicion)
    ediciones = sorted(ediciones, reverse=True)

    opciones = []
    for edicion in ediciones:
        for resolucion in PRIORIDAD_RESOLUCION:
            for formato in PRIORIDAD_FORMATO:
                for fila in del_tipo:
                    if edicion_de(fila) != edicion:
                        continue
                    if fila["Resolucion"].strip() != resolucion:
                        continue
                    if fila[formato].strip() == "":
                        continue
                    enlace = armar_enlace(fila, formato)
                    opciones.append({"resolucion": resolucion, "formato": formato,
                                     "edicion": edicion, "enlace": enlace})
    return opciones


def buscar_raster(carpeta, formato):
    for raiz, subcarpetas, archivos in os.walk(carpeta):
        for nombre in archivos:
            minuscula = nombre.lower()
            if formato == "bil" and minuscula.endswith(".bil"):
                return os.path.join(raiz, nombre)
            if formato == "tif" and minuscula.endswith(".tif"):
                return os.path.join(raiz, nombre)
            if formato == "ascii" and minuscula.endswith(".xyz"):
                return os.path.join(raiz, nombre)
            if formato == "grid" and minuscula == "hdr.adf":
                return os.path.join(raiz, nombre)
    return None


def nombre_base(clave, tipo, resolucion):
    return clave + "_" + tipo + "_" + resolucion.replace(".", "_") + "m"


def descargar_zip(enlace, destino):
    """Devuelve (True, "") si descargó un .zip válido, o (False, motivo)."""
    if not enlace.lower().startswith("https://"):
        return False, "enlace no permitido (solo https)"
    try:
        with ABRIDOR.open(enlace, timeout=60) as respuesta:
            with open(destino, "wb") as archivo:
                shutil.copyfileobj(respuesta, archivo)
    except urllib.error.HTTPError as error:
        return False, "HTTP " + str(error.code)
    if not zipfile.is_zipfile(destino):
        return False, "no es un .zip"
    return True, ""


def procesar_carta(tabla, clave, tipo, carpeta_salida):
    clave = clave.strip().upper()
    if clave not in tabla:
        return "la clave no está en el CSV", None

    opciones = opciones_en_orden(tabla, clave, tipo)
    if len(opciones) == 0:
        return "sin opción disponible", None

    for opcion in opciones:
        nombre = nombre_base(clave, tipo, opcion["resolucion"])
        archivo_tif = os.path.join(carpeta_salida, nombre + ".tif")
        if os.path.exists(archivo_tif):
            return "ya existía, no se descargó de nuevo", archivo_tif

    carpeta_temp = os.path.join(carpeta_salida, "_temp_" + clave)
    carpeta_extraccion = os.path.join(carpeta_temp, "datos")
    archivo_zip = os.path.join(carpeta_temp, "descarga.zip")
    archivo_resultado = os.path.join(carpeta_temp, "resultado.tif")
    os.makedirs(carpeta_temp, exist_ok=True)

    origen = None
    resultado = None
    try:
        elegida = None
        fallos = []
        for opcion in opciones:
            ok, motivo = descargar_zip(opcion["enlace"], archivo_zip)
            if ok:
                elegida = opcion
                break
            fallos.append(opcion["formato"] + " " + opcion["resolucion"] + " m (" + motivo + ")")

        if elegida is None:
            return "ninguna opción se pudo descargar: " + "; ".join(fallos), None

        with zipfile.ZipFile(archivo_zip) as z:
            z.extractall(carpeta_extraccion)

        ruta_raster = buscar_raster(carpeta_extraccion, elegida["formato"])
        if ruta_raster is None:
            return "no encontré el ráster dentro del .zip", None

        origen = gdal.Open(ruta_raster)
        if origen is None:
            return "GDAL no pudo abrir el ráster", None

        resultado = gdal.Translate(
            archivo_resultado, origen, format="GTiff",
            creationOptions=opciones_creacion(origen.GetRasterBand(1).DataType))
        if resultado is None:
            return "GDAL no pudo convertir el ráster", None

        igual_tamano = (origen.RasterXSize == resultado.RasterXSize and
                        origen.RasterYSize == resultado.RasterYSize)
        igual_posicion = origen.GetGeoTransform() == resultado.GetGeoTransform()
        igual_crs = (origen.GetProjection() == "") == (resultado.GetProjection() == "")
        origen = None
        resultado = None

        nombre = nombre_base(clave, tipo, elegida["resolucion"])
        archivo_tif = os.path.join(carpeta_salida, nombre + ".tif")
        os.replace(archivo_resultado, archivo_tif)

        estado = ("listo: " + elegida["resolucion"] + " m, " + elegida["formato"] +
                  ", edición " + elegida["edicion"])
        if len(fallos) > 0:
            estado = estado + " (antes falló: " + "; ".join(fallos) + ")"
        if not (igual_tamano and igual_posicion and igual_crs):
            estado = estado + " (REVISAR: la verificación detectó diferencias)"
        return estado, archivo_tif
    finally:
        origen = None
        resultado = None
        shutil.rmtree(carpeta_temp, ignore_errors=True)