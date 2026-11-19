# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import QgsTask


from . import procesamiento


class TareaProcesar(QgsTask):
    rasterTerminado = pyqtSignal(str)

    def __init__(self, rutas, hacer_limpieza, margen, hacer_warp, resolucion, nodata, respaldar, al_terminar):
        super(TareaProcesar, self).__init__("Procesar rásteres de INEGI", QgsTask.Flag.CanCancel)
        self.rutas = rutas
        self.hacer_limpieza = hacer_limpieza
        self.margen = margen
        self.hacer_warp = hacer_warp
        self.resolucion = resolucion
        self.nodata = nodata
        self.respaldar = respaldar
        self.al_terminar = al_terminar

    def run(self):
        total = len(self.rutas)
        for numero, ruta in enumerate(self.rutas, start=1):
            if self.isCanceled():
                return False

            nombre = os.path.basename(ruta)
            texto_respaldo = ""
            if self.respaldar:
                try:
                    texto_respaldo = procesamiento.respaldar(ruta) + " | "
                except Exception as error:
                    self.rasterTerminado.emit(
                        nombre + " -> no se pudo respaldar; no se procesó: " + str(error))
                    self.setProgress(numero * 100.0 / total)
                    continue

            try:
                estado = procesamiento.procesar_raster(
                    ruta, self.hacer_limpieza, self.margen,
                    self.hacer_warp, self.resolucion, self.nodata)
            except Exception as error:
                estado = "ERROR: " + str(error)

            self.rasterTerminado.emit(nombre + " -> " + texto_respaldo + estado)
            self.setProgress(numero * 100.0 / total)
        return True

    def finished(self, resultado):
        self.al_terminar(self, resultado)