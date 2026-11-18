# -*- coding: utf-8 -*-
from osgeo import gdal


def opciones_creacion(tipo_dato):
    opciones = ["COMPRESS=DEFLATE", "TILED=YES"]
    if tipo_dato in (gdal.GDT_Float32, gdal.GDT_Float64):
        opciones.append("PREDICTOR=3")
    elif tipo_dato in (gdal.GDT_Byte, gdal.GDT_UInt16, gdal.GDT_Int16,
                       gdal.GDT_UInt32, gdal.GDT_Int32):
        opciones.append("PREDICTOR=2")
    return opciones