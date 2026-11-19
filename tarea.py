# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import QgsTask

from . import descarga


class TareaDescarga(QgsTask):
    cartaTerminada = pyqtSignal(str)

    def __init__(self, tabla, claves, tipo, carpeta_salida, al_terminar):
        super(TareaDescarga, self).__init__("Descarga de MDE INEGI", QgsTask.Flag.CanCancel)
        self.tabla = tabla
        self.claves = claves
        self.tipo = tipo
        self.carpeta_salida = carpeta_salida
        self.al_terminar = al_terminar
        self.resultados = []

    def run(self):
        total = len(self.claves)
        for numero, clave in enumerate(self.claves, start=1):
            if self.isCanceled():
                return False

            try:
                estado, ruta_tif = descarga.procesar_carta(
                    self.tabla, clave, self.tipo, self.carpeta_salida)
            except Exception as error:
                estado, ruta_tif = "ERROR: " + str(error), None

            self.resultados.append((clave, estado, ruta_tif))
            self.cartaTerminada.emit(clave + " -> " + estado)
            self.setProgress(numero * 100.0 / total)
        return True

    def finished(self, resultado):
        self.al_terminar(self, resultado)