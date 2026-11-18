# -*- coding: utf-8 -*-
"""Procesos sobre los .tif de INEGI: limpiar márgenes y warp a ITRF2008.
Solo usa GDAL, así que se puede ejecutar en segundo plano."""
import os
import re
import time
import uuid
import shutil

from osgeo import gdal, ogr, osr

MARCA_LIMPIEZA = "MDE_INEGI_MARGEN_LIMPIADO"
CARPETA_RESPALDO = "respaldo_original"


def respaldar(ruta_tif):
    """Copia el .tif a la subcarpeta de respaldo, sin sobrescribir uno que ya exista."""
    carpeta = os.path.join(os.path.dirname(ruta_tif), CARPETA_RESPALDO)
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, os.path.basename(ruta_tif))
    if os.path.exists(destino):
        return "respaldo ya existía (se conserva el anterior)"

    temporal = destino + ".tmp"
    shutil.copy2(ruta_tif, temporal)
    os.replace(temporal, destino)

    auxiliar = ruta_tif + ".aux.xml"
    if os.path.exists(auxiliar):
        shutil.copy2(auxiliar, destino + ".aux.xml")
    return "respaldo creado"


def opciones_creacion(tipo_dato):
    opciones = ["COMPRESS=DEFLATE", "TILED=YES"]
    if tipo_dato in (gdal.GDT_Float32, gdal.GDT_Float64):
        opciones.append("PREDICTOR=3")
    elif tipo_dato in (gdal.GDT_Byte, gdal.GDT_UInt16, gdal.GDT_Int16,
                       gdal.GDT_UInt32, gdal.GDT_Int32):
        opciones.append("PREDICTOR=2")
    return opciones


def reemplazar(ruta_temporal, ruta_destino):
    for intento in range(10):
        try:
            os.replace(ruta_temporal, ruta_destino)
            return True
        except PermissionError:
            time.sleep(0.5)
    return False


def limpiar_margen(ruta_tif, margen, nodata):
    origen = gdal.Open(ruta_tif)
    if origen is None:
        return False, "no pude abrir el ráster"

    ya_limpio = origen.GetMetadataItem(MARCA_LIMPIEZA)
    if ya_limpio:
        origen = None
        return True, "ya estaba limpia (margen de " + ya_limpio + " m); no se tocó"

    geotransformacion = origen.GetGeoTransform()
    celda_x = geotransformacion[1]
    celda_y = abs(geotransformacion[5])
    ancho = origen.RasterXSize
    alto = origen.RasterYSize
    tipo_dato = origen.GetRasterBand(1).DataType

    identificador = uuid.uuid4().hex
    huella_vsi = "/vsimem/huella_" + identificador + ".shp"
    corte_vsi = "/vsimem/corte_" + identificador + ".shp"
    carpeta = os.path.dirname(ruta_tif)
    nombre = os.path.splitext(os.path.basename(ruta_tif))[0]
    ruta_temporal = os.path.join(carpeta, nombre + "_limpio.tmp.tif")
    controlador = ogr.GetDriverByName("ESRI Shapefile")

    try:
        # 1. Polígono con el contorno de las celdas que tienen dato
        fuente = controlador.CreateDataSource(huella_vsi)
        capa = fuente.CreateLayer("huella", geom_type=ogr.wkbPolygon)
        capa.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))

        mascara = origen.GetRasterBand(1).GetMaskBand()
        memoria = gdal.GetDriverByName("MEM").Create("", ancho, alto, 1, gdal.GDT_Byte)
        memoria.SetGeoTransform(geotransformacion)
        banda_memoria = memoria.GetRasterBand(1)
        banda_memoria.WriteArray(mascara.ReadAsArray())
        gdal.Polygonize(banda_memoria, banda_memoria, capa, 0)
        banda_memoria = None
        memoria = None

        union = ogr.Geometry(ogr.wkbMultiPolygon)
        capa.ResetReading()
        for entidad in capa:
            union.AddGeometry(entidad.GetGeometryRef().Clone())
        entidad = None
        capa = None
        fuente = None
        if union.GetGeometryCount() == 0:
            return False, "el ráster no tiene celdas con dato; no se tocó"
        if hasattr(union, "UnaryUnion"):
            union = union.UnaryUnion()
        else:
            union = union.UnionCascaded()

        # 2. Reducir el contorno en "margen" metros
        reducida = union.Buffer(-margen, 5)
        if reducida is None or reducida.IsEmpty():
            return False, "el margen de " + str(margen) + " m es mayor que la carta; no se tocó"

        corte = controlador.CreateDataSource(corte_vsi)
        capa_corte = corte.CreateLayer("corte", geom_type=ogr.wkbPolygon)
        entidad_corte = ogr.Feature(capa_corte.GetLayerDefn())
        entidad_corte.SetGeometry(reducida)
        capa_corte.CreateFeature(entidad_corte)
        entidad_corte = None
        capa_corte = None
        corte = None

        # 3. Recortar el ráster con ese contorno
        opciones = gdal.WarpOptions(
            format="GTiff", cutlineDSName=corte_vsi, cropToCutline=True,
            xRes=celda_x, yRes=celda_y, targetAlignedPixels=True,
            dstNodata=nodata, creationOptions=opciones_creacion(tipo_dato))
        resultado = gdal.Warp(ruta_temporal, origen, options=opciones)
        if resultado is None:
            return False, "GDAL no pudo recortar el ráster"
        resultado = None
        origen = None

        # 4. Marcar el resultado como ya limpiado
        actualizado = gdal.Open(ruta_temporal, gdal.GA_Update)
        if actualizado is None:
            return False, "no pude abrir el resultado para marcarlo"
        actualizado.SetMetadataItem(MARCA_LIMPIEZA, str(margen))
        actualizado = None

        # 5. Reemplazar el original
        if not reemplazar(ruta_temporal, ruta_tif):
            return False, "no pude reemplazar el original (¿sigue abierto en otro programa?); no se guardó nada"

        return True, "margen de " + str(margen) + " m recortado"
    finally:
        origen = None
        for base in (huella_vsi, corte_vsi):
            for extension in (".shp", ".shx", ".dbf"):
                gdal.Unlink(base[:-4] + extension)
        if os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
            except OSError:
                pass


def warp(ruta_tif, resolucion, nodata):
    nombre_archivo = os.path.basename(ruta_tif)
    clave = nombre_archivo[:8].upper()

    try:
        zona_clave = int(clave[1:3])
    except ValueError:
        return False, "no pude leer la zona de la clave " + clave + "; no se tocó"
    if zona_clave < 11 or zona_clave > 16:
        return False, "la zona " + str(zona_clave) + " está fuera de 11 a 16; no se tocó"
    destino = "EPSG:" + str(6355 + zona_clave)

    origen = gdal.Open(ruta_tif)
    if origen is None:
        return False, "no pude abrir el ráster"
    wkt = origen.GetProjection()
    gt_origen = origen.GetGeoTransform()
    celda = gt_origen[1]
    banda = origen.GetRasterBand(1)
    nodata_actual = banda.GetNoDataValue()
    tipo_actual = gdal.GetDataTypeName(banda.DataType)
    marca = origen.GetMetadataItem(MARCA_LIMPIEZA)
    banda = None
    origen = None

    if wkt == "":
        crs_origen = destino
        aviso = " (sin CRS de origen: se asignó " + destino + ")"
        ya_en_destino = False
    else:
        srs = osr.SpatialReference()
        srs.ImportFromWkt(wkt)
        nombre_crs = srs.GetName()
        coincidencia = re.search(r"zone[_ ]?(\d+)", nombre_crs, re.IGNORECASE)
        if coincidencia is None:
            return False, "no pude leer la zona del CRS (" + nombre_crs + "); no se tocó"
        zona_archivo = int(coincidencia.group(1))
        if zona_archivo != zona_clave:
            return False, ("la zona del archivo (" + str(zona_archivo) +
                           ") no coincide con la de la clave (" + str(zona_clave) + "); no se tocó")
        crs_origen = None
        aviso = ""
        ya_en_destino = "2008" in nombre_crs

    if (ya_en_destino and abs(celda - resolucion) < 0.000001
            and nodata_actual == nodata and tipo_actual == "Float32"):
        return True, "ya estaba igual (CRS, resolución, NoData y tipo); no se tocó"

    carpeta = os.path.dirname(ruta_tif)
    nombre = os.path.splitext(nombre_archivo)[0]
    ruta_temporal = os.path.join(carpeta, nombre + "_warp.tmp.tif")

    try:
        opciones = gdal.WarpOptions(
            format="GTiff", srcSRS=crs_origen, dstSRS=destino,
            xRes=resolucion, yRes=resolucion, resampleAlg="lanczos",
            dstNodata=nodata, outputType=gdal.GDT_Float32,
            creationOptions=opciones_creacion(gdal.GDT_Float32))
        resultado = gdal.Warp(ruta_temporal, ruta_tif, options=opciones)
        if resultado is None:
            return False, "GDAL no pudo hacer el warp"
        gt_nuevo = resultado.GetGeoTransform()
        if marca:
            resultado.SetMetadataItem(MARCA_LIMPIEZA, marca)
        resultado = None

        movimiento = max(abs(gt_nuevo[0] - gt_origen[0]), abs(gt_nuevo[3] - gt_origen[3]))
        tolerancia = max(celda, resolucion)

        if not reemplazar(ruta_temporal, ruta_tif):
            return False, "no pude reemplazar el original (¿sigue abierto en otro programa?); no se guardó nada"

        texto = destino + ", celda " + str(resolucion) + " m" + aviso
        if movimiento > tolerancia:
            texto = texto + " (REVISAR: la esquina del ráster se movió " + str(movimiento) + " m)"
        return True, texto
    finally:
        if os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
            except OSError:
                pass


def procesar_raster(ruta_tif, hacer_limpieza, margen, hacer_warp, resolucion, nodata):
    """Aplica los procesos elegidos, en orden, y devuelve un texto para el reporte."""
    partes = []
    if hacer_limpieza:
        ok, texto = limpiar_margen(ruta_tif, margen, nodata)
        partes.append("limpieza: " + texto)
        if not ok:
            return " | ".join(partes)
    if hacer_warp:
        ok, texto = warp(ruta_tif, resolucion, nodata)
        partes.append("warp: " + texto)
    return " | ".join(partes)