# -*- coding: utf-8 -*-
import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer

from .tarea_procesar import TareaProcesar

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'procesar_dialog_base.ui'))

AYUDA = """
<h3>Procesar rásteres</h3>
<p>Prepara los GeoTIFF de los MDE de INEGI para usarlos.
<b>Los archivos originales se reemplazan</b> por los resultados.</p>

<p><b>Entrada</b></p>
<p>Las capas cargadas que marques en la lista, o todos los .tif de una
carpeta. El nombre de cada archivo debe empezar con la clave de la carta,
como los deja la herramienta de descarga.</p>

<p><b>Limpiar márgenes</b></p>
<p>Recorta hacia adentro el borde de la carta, donde INEGI tiene valores
inconsistentes, la distancia indicada en metros. Una carta que ya se
limpió no se vuelve a recortar.</p>

<p><b>Warp a ITRF2008</b></p>
<p>Lleva el ráster al ITRF2008 UTM de la zona que indica la clave (sus
caracteres 2.º y 3.º), con remuestreo Lanczos, datos Float32 y la
resolución indicada. Si el archivo no tiene sistema de coordenadas, se
le asigna; si su zona no coincide con la de la clave, se omite.</p>

<p><b>NoData</b></p>
<p>Valor para las celdas sin dato, en los dos procesos (por defecto −9999).</p>

<p><b>Notas</b></p>
<ul>
<li>Si activas los dos procesos, primero se limpia y después se hace el warp.</li>
<li>Las capas cargadas se quitan mientras se procesan y vuelven al terminar.</li>
<li>Detener espera a que termine el archivo en curso.</li>
</ul>
"""

def normalizar(ruta):
    return os.path.normcase(os.path.normpath(ruta))


def quitar_capas(rutas):
    """Quita del proyecto las capas que usan alguno de estos archivos.
    Devuelve una lista de pares (ruta del archivo, nombre de la capa)."""
    objetivos = {}
    for ruta in rutas:
        objetivos[normalizar(ruta)] = ruta

    quitadas = []
    for capa in list(QgsProject.instance().mapLayers().values()):
        if isinstance(capa, QgsRasterLayer):
            fuente = normalizar(capa.source())
            if fuente in objetivos:
                quitadas.append((objetivos[fuente], capa.name()))
                QgsProject.instance().removeMapLayer(capa.id())
    return quitadas


def cargar_capas(quitadas):
    for ruta, nombre in quitadas:
        nueva = QgsRasterLayer(ruta, nombre)
        if nueva.isValid():
            QgsProject.instance().addMapLayer(nueva)


class ProcesarDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(ProcesarDialog, self).__init__(parent)
        self.setupUi(self)
        self.textBrowser_ayuda.setHtml(AYUDA)

        self.tarea = None
        self.capas_quitadas = []

        self.doubleSpinBox_nodata.setRange(-1000000000, 1000000000)
        self.doubleSpinBox_nodata.setDecimals(0)
        self.doubleSpinBox_nodata.setValue(-9999)

        self.doubleSpinBox_margen.setRange(0, 5000)
        self.doubleSpinBox_margen.setDecimals(1)
        self.doubleSpinBox_margen.setValue(20)
        self.doubleSpinBox_margen.setSuffix(" m")

        self.doubleSpinBox_resolucion.setRange(0.1, 1000)
        self.doubleSpinBox_resolucion.setDecimals(2)
        self.doubleSpinBox_resolucion.setValue(5)
        self.doubleSpinBox_resolucion.setSuffix(" m")

        self.groupBox_limpiar.setChecked(False)
        self.groupBox_warp.setChecked(False)
        self.checkBox_respaldo.setChecked(False)
        self.radioButton_capas.setChecked(True)
        self.btn_cancelar.setEnabled(False)
        self.progressBar.setValue(0)

        self.radioButton_capas.toggled.connect(self.actualizar_origen)
        self.btn_marcar_todas.clicked.connect(self.marcar_todas)
        self.btn_marcar_ninguna.clicked.connect(self.marcar_ninguna)
        self.btn_carpeta.clicked.connect(self.elegir_carpeta)
        self.btn_ejecutar.clicked.connect(self.ejecutar)
        self.btn_cancelar.clicked.connect(self.cancelar)
        QgsProject.instance().layersAdded.connect(self.al_cambiar_capas_del_proyecto)
        QgsProject.instance().layersRemoved.connect(self.al_cambiar_capas_del_proyecto)

        self.actualizar_origen()

    def showEvent(self, evento):
        """Se ejecuta cada vez que la ventana se muestra."""
        super(ProcesarDialog, self).showEvent(evento)
        if self.tarea is None:
            self.textEdit_reporte.clear()
            self.progressBar.setValue(0)
            self.llenar_lista_capas()

    def mostrar_aviso(self, texto):
        QtWidgets.QMessageBox.warning(self, "MDE INEGI", texto)

    def actualizar_origen(self, estado=None):
        usar_capas = self.radioButton_capas.isChecked()
        self.listWidget_capas.setEnabled(usar_capas)
        self.btn_marcar_todas.setEnabled(usar_capas)
        self.btn_marcar_ninguna.setEnabled(usar_capas)
        self.lineEdit_carpeta.setEnabled(not usar_capas)
        self.btn_carpeta.setEnabled(not usar_capas)

    def llenar_lista_capas(self, automatico=False):
        """Llena la lista con los rásteres .tif cargados.
        Si es automático (por un cambio en el proyecto), conserva las casillas marcadas."""
        marcadas = set()
        if automatico:
            for i in range(self.listWidget_capas.count()):
                elemento = self.listWidget_capas.item(i)
                if elemento.checkState() == Qt.CheckState.Checked:
                    marcadas.add(normalizar(elemento.data(Qt.ItemDataRole.UserRole)))

        self.listWidget_capas.clear()
        omitidas = 0
        for capa in QgsProject.instance().mapLayers().values():
            if not isinstance(capa, QgsRasterLayer):
                continue
            fuente = capa.source()
            if fuente.lower().endswith(".tif") and os.path.isfile(fuente):
                elemento = QtWidgets.QListWidgetItem(capa.name())
                elemento.setFlags(elemento.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if normalizar(fuente) in marcadas:
                    elemento.setCheckState(Qt.CheckState.Checked)
                else:
                    elemento.setCheckState(Qt.CheckState.Unchecked)
                elemento.setData(Qt.ItemDataRole.UserRole, fuente)
                elemento.setToolTip(fuente)
                self.listWidget_capas.addItem(elemento)
            else:
                omitidas += 1

        if not automatico:
            texto = "Rásteres cargados utilizables: " + str(self.listWidget_capas.count())
            if omitidas > 0:
                texto = texto + " (omitidos " + str(omitidas) + " que no son un .tif en disco)"
            self.textEdit_reporte.appendPlainText(texto)

    def al_cambiar_capas_del_proyecto(self, *args):
        """Se ejecuta cuando se cargan o se quitan capas del proyecto."""
        if self.isVisible():
            self.llenar_lista_capas(automatico=True)

    def cambiar_marcas(self, estado):
        for i in range(self.listWidget_capas.count()):
            self.listWidget_capas.item(i).setCheckState(estado)

    def marcar_todas(self):
        self.cambiar_marcas(Qt.CheckState.Checked)

    def marcar_ninguna(self):
        self.cambiar_marcas(Qt.CheckState.Unchecked)

    def elegir_carpeta(self):
        carpeta = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta con los .tif")
        if carpeta:
            self.lineEdit_carpeta.setText(carpeta)

    def rutas_de_entrada(self):
        rutas = []
        if self.radioButton_capas.isChecked():
            for i in range(self.listWidget_capas.count()):
                elemento = self.listWidget_capas.item(i)
                if elemento.checkState() == Qt.CheckState.Checked:
                    ruta = elemento.data(Qt.ItemDataRole.UserRole)
                    if ruta not in rutas:
                        rutas.append(ruta)
        else:
            carpeta = self.lineEdit_carpeta.text().strip()
            if os.path.isdir(carpeta):
                for nombre in sorted(os.listdir(carpeta)):
                    minuscula = nombre.lower()
                    if minuscula.endswith(".tif") and not minuscula.endswith(".tmp.tif"):
                        rutas.append(os.path.join(carpeta, nombre))
        return rutas

    def ejecutar(self):
        hacer_limpieza = self.groupBox_limpiar.isChecked()
        hacer_warp = self.groupBox_warp.isChecked()
        if not hacer_limpieza and not hacer_warp:
            self.mostrar_aviso("Activa al menos un proceso: limpiar márgenes o warp.")
            return

        rutas = self.rutas_de_entrada()
        if len(rutas) == 0:
            self.mostrar_aviso("No hay rásteres seleccionados.")
            return

        nodata = int(self.doubleSpinBox_nodata.value())
        margen = self.doubleSpinBox_margen.value()
        resolucion = self.doubleSpinBox_resolucion.value()

        self.textEdit_reporte.clear()
        self.progressBar.setValue(0)
        self.btn_ejecutar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)

        respaldar = self.checkBox_respaldo.isChecked()
        self.tarea = TareaProcesar(rutas, hacer_limpieza, margen, hacer_warp,
                                   resolucion, nodata, respaldar, self.tarea_terminada)
        if respaldar:
            self.textEdit_reporte.appendPlainText(
                "Los originales se respaldan en la subcarpeta respaldo_original.")
        
        self.tarea.rasterTerminado.connect(self.textEdit_reporte.appendPlainText)
        self.tarea.progressChanged.connect(self.actualizar_progreso)

        self.capas_quitadas = quitar_capas(rutas)
        if len(self.capas_quitadas) > 0:
            self.textEdit_reporte.appendPlainText(
                "Se quitaron del proyecto " + str(len(self.capas_quitadas)) +
                " capa(s) mientras se procesan; se volverán a cargar al terminar.")

        QgsApplication.taskManager().addTask(self.tarea)

    def actualizar_progreso(self, valor):
        self.progressBar.setValue(int(valor))

    def cancelar(self):
        if self.tarea is not None:
            self.tarea.cancel()
            self.textEdit_reporte.appendPlainText(
                "Deteniendo... se detendrá al terminar el ráster en curso.")
            self.btn_cancelar.setEnabled(False)

    def tarea_terminada(self, tarea, exito):
        self.btn_ejecutar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)

        if exito:
            self.progressBar.setValue(100)
        else:
            self.textEdit_reporte.appendPlainText("--- Proceso detenido ---")

        cargar_capas(self.capas_quitadas)
        if len(self.capas_quitadas) > 0:
            self.textEdit_reporte.appendPlainText(
                "Se volvieron a cargar " + str(len(self.capas_quitadas)) + " capa(s).")

        self.capas_quitadas = []
        self.tarea = None