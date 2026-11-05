# Generación del documento oficial "Acción de Personal" (Fase 19).
#
# Reproduce la plantilla Excel oficial de SETESA (Hoja1): mismos anchos de
# columna, alto de filas, bordes, fuentes y posición del logo, con la escala de
# impresión de la plantilla (95 %). Las medidas salen del propio .xlsx:
#   - Columnas A..I en caracteres de Excel -> píxeles -> mm.
#   - Filas en puntos -> mm (alto por defecto 12.75 pt).
# Diferencias deliberadas con la hoja impresa a mano:
#   - Las filas 49-50 son más altas para que quepan las firmas digitales.
#   - Debajo de las firmas se agregan los nombres, la resolución y un pie con
#     el número de expediente (la hoja manual no los tiene).

import datetime
import os
from uuid import uuid4

from fpdf import FPDF

from src.core.config import PDF_DIR, PROJECT_ROOT, ensure_dirs
from src.core.workflow import ESTADO_FINALIZADA, ESTADO_PENDIENTE_APROBACION_GERENCIA
from src.services.utils_firma import base64_to_image, eliminar_archivo

LOGO = PROJECT_ROOT / "assets" / "logo_setesa.png"

ESCALA = 0.95                      # escala de impresión de la plantilla
MM_POR_PX = 25.4 / 96 * ESCALA     # columnas: píxeles de Excel a mm
MM_POR_PT = 25.4 / 72 * ESCALA     # filas y fuentes: puntos a mm
MARGEN_IZQ = 7.6                   # 0.3 pulgadas
MARGEN_SUP = 6.0

# Ancho de columnas A..I en caracteres (xl/worksheets/sheet1.xml).
_ANCHOS_EXCEL = [0.5703125, 2.28515625, 31.42578125, 1.85546875, 2.0,
                 24.28515625, 1.85546875, 1.7109375, 35.42578125]
COLUMNAS = "ABCDEFGHI"


def _px(ancho):
    # Conversión de Excel (fuente Arial 10, dígito de 7 px).
    return int((256 * ancho + int(128 / 7)) / 256 * 7)


ANCHO_COL = {c: _px(a) * MM_POR_PX for c, a in zip(COLUMNAS, _ANCHOS_EXCEL)}
X_COL = {}
_x = MARGEN_IZQ
for _c in COLUMNAS:
    X_COL[_c] = _x
    _x += ANCHO_COL[_c]
X_FIN = _x

# Alto de filas en puntos (las que no aparecen usan 12.75).
_ALTOS_PT = {
    2: 14.25, 9: 13.5, 10: 16.5, 11: 12, 12: 12, 13: 16.5, 14: 12, 15: 12,
    16: 21, 17: 9, 18: 13.5, 19: 7.5, 21: 6, 23: 6.75, 25: 6, 27: 6.75,
    29: 6, 31: 6.75, 33: 6.75, 35: 6.75, 36: 18, 37: 6.75, 38: 12,
    **{f: 12.95 for f in range(39, 49)},
    49: 22, 50: 22, 51: 12, 52: 12, 53: 12, 54: 12,
    **{f: 12 for f in (20, 22, 24, 26, 28, 30, 32, 34)},
}
Y_FILA = {}
ALTO_FILA = {}
_y = MARGEN_SUP
for _f in range(1, 61):
    ALTO_FILA[_f] = _ALTOS_PT.get(_f, 12.75) * MM_POR_PT
    Y_FILA[_f] = _y
    _y += ALTO_FILA[_f]

# Cuadrícula "NATURALEZA DE LA ACCION": (fila, opción) por columna de casillas.
CUADRICULA = [
    (20, "PERMISO CON GOCE DE SUELDO", "MATRIMONIO", "EVALUACION DEL DESEMPEÑO"),
    (22, "PERMISO SIN GOCE DE SUELDO", "RENUNCIA", "CALIFICACION DE MERITO"),
    (24, "LLEGADA TARDIA", "DESPIDO", "ASCENSO"),
    (26, "FALTA INJUSTIFICADA", "AMONESTACION VERBAL", "TRASLADO"),
    (28, "ABANDONO DE LABORES", "AMONESTACION ESCRITA", "NACIMIENTO DE HIJO (A)"),
    (30, "SUSPENSIÓN IGSS", "DESCONTAR SEPTIMO", "OTROS"),
    (32, "VACACION", "SUSPENSION", None),
    (34, "DUELO", "CONTRATACION", None),
]
# Columna de la casilla y de su texto, por bloque.
_BLOQUES = (("B", "C"), ("E", "F"), ("H", "I"))


def _logo_plano():
    """Logo sin transparencia (sobre blanco), en caché junto a los PDF.

    Con canal alfa FPDF incrusta dos imágenes (imagen y máscara); aplanado,
    el PDF es más liviano y el logo es una sola imagen.
    """
    if not LOGO.exists():
        return None
    ensure_dirs()
    destino = PDF_DIR / ".logo_setesa.jpg"
    if not destino.exists() or destino.stat().st_mtime < LOGO.stat().st_mtime:
        from PIL import Image

        with Image.open(LOGO) as imagen:
            imagen = imagen.convert("RGBA")
            fondo = Image.new("RGB", imagen.size, (255, 255, 255))
            fondo.paste(imagen, mask=imagen.split()[3])
            fondo.save(destino, "JPEG", quality=92)
    return destino


def limpiar_nombre(nombre_crudo):
    """Elimina etiquetas como '(Consultor)' del nombre para estampar en la firma."""
    nombre_crudo = nombre_crudo or ""
    return nombre_crudo.split(" (")[0] if " (" in nombre_crudo else nombre_crudo


def _segmento_archivo(texto):
    import re

    limpio = re.sub(r"[^A-Za-z0-9_-]+", "_", texto).strip("_")
    return limpio or "empleado"


def _tiene_firma(firma_b64):
    return bool(firma_b64 and isinstance(firma_b64, str) and firma_b64.strip())


def formato_fecha(valor):
    """dd/mm/aaaa a partir de date, datetime o texto ISO."""
    if valor is None or valor == "":
        return ""
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor).split()[0].split("T")[0]
    try:
        return datetime.date.fromisoformat(texto).strftime("%d/%m/%Y")
    except ValueError:
        return texto


def _latin1(texto):
    """FPDF 1.7 usa latin-1: reemplaza lo que no se pueda representar."""
    return (texto or "").encode("latin-1", "replace").decode("latin-1")


class _Hoja:
    """Dibuja sobre la cuadrícula de la plantilla."""

    def __init__(self):
        self.pdf = FPDF("P", "mm", "A4")
        self.pdf.set_auto_page_break(False)
        self.pdf.set_margins(0, 0, 0)
        self.pdf.add_page()
        self.pdf.set_line_width(0.2)

    # Fuentes en puntos de Excel, escaladas como en la impresión.
    def fuente(self, tamano=9, estilo=""):
        self.pdf.set_font("Arial", estilo, tamano * ESCALA)

    def ancho_texto(self, texto):
        return self.pdf.get_string_width(_latin1(texto))

    def texto(self, x, fila, texto, ancho=0, alinear="L", tamano=9, estilo=""):
        """Escribe alineado a la base de la fila (como Excel)."""
        self.fuente(tamano, estilo)
        alto = tamano * MM_POR_PT * 1.15
        y = Y_FILA[fila] + ALTO_FILA[fila] - alto
        self.pdf.set_xy(x, y)
        self.pdf.cell(ancho, alto, _latin1(texto), 0, 0, alinear)

    def linea(self, x1, y1, x2, y2):
        self.pdf.line(x1, y1, x2, y2)

    def borde(self, col, fila, lados):
        x1, x2 = X_COL[col], X_COL[col] + ANCHO_COL[col]
        y1, y2 = Y_FILA[fila], Y_FILA[fila] + ALTO_FILA[fila]
        if "l" in lados:
            self.linea(x1, y1, x1, y2)
        if "r" in lados:
            self.linea(x2, y1, x2, y2)
        if "t" in lados:
            self.linea(x1, y1, x2, y1)
        if "b" in lados:
            self.linea(x1, y2, x2, y2)

    def campo(self, x, fila, etiqueta, valor, x_fin, tamano=9):
        """Etiqueta seguida de una línea con el valor escrito encima."""
        self.texto(x, fila, etiqueta, tamano=tamano)
        inicio = x + self.ancho_texto(etiqueta) + 1
        base = Y_FILA[fila] + ALTO_FILA[fila] - 0.6
        self.linea(inicio, base, x_fin, base)
        self.pdf.set_xy(inicio + 1, base - 4.2)
        self.fuente(tamano, "B")
        self.pdf.cell(x_fin - inicio - 1, 4, _latin1(valor), 0, 0, "L")


def _dibujar_marco(hoja):
    """Bordes de "NATURALEZA DE LA ACCION" y de la explicación (estilos de la hoja)."""
    for c in COLUMNAS:
        lados = "tb" + ("l" if c == "A" else "") + ("r" if c == "I" else "")
        hoja.borde(c, 18, lados)
    for fila in range(19, 39):
        hoja.borde("A", fila, "l")
        for c in ("C", "F", "I"):
            hoja.borde(c, fila, "r")
    for c in COLUMNAS:
        hoja.borde(c, 38, "b")
    for fila in range(39, 49):
        hoja.borde("A", fila, "l")
        hoja.borde("I", fila, "r")
    for c in COLUMNAS:
        hoja.borde(c, 39, "t")
        hoja.borde(c, 48, "b")


def generar_pdf_accion_personal(nombre_empleado, jefe_gtc, puesto, codigo, tipo_ausencia, fecha_inicio, fecha_fin, dias, explicacion, estado_workflow="Ingresada", fecha_creacion=None, firma_empleado_b64=None, firma_jefe_b64=None, firma_gerencia_b64=None, id_solicitud=None, resolucion=None, motivo_resolucion=None, denegada_por=None):
    hoja = _Hoja()
    pdf = hoja.pdf
    nombre_emp = limpiar_nombre(nombre_empleado)
    jefe = limpiar_nombre(jefe_gtc)
    fecha_doc = formato_fecha(fecha_creacion or datetime.date.today())

    # --- Encabezado: logo (C1) y título (C7:I8) ------------------------------
    logo = _logo_plano()
    if logo:
        pdf.image(str(logo), x=X_COL["C"], y=MARGEN_SUP, w=61.0 * ESCALA, h=20.85 * ESCALA)
    else:
        hoja.texto(X_COL["C"], 3, "SETESA", tamano=16, estilo="B")
    hoja.fuente(20, "B")
    alto_titulo = ALTO_FILA[7] + ALTO_FILA[8]
    pdf.set_xy(X_COL["C"], Y_FILA[7])
    pdf.cell(X_FIN - X_COL["C"], alto_titulo, "ACCION DE PERSONAL", 0, 0, "C")

    # --- Datos generales -----------------------------------------------------
    hoja.campo(X_COL["B"], 10, "DE:", nombre_emp, X_FIN)
    hoja.texto(X_COL["B"], 11, "(NOMBRE DEL EMPLEADO)", X_FIN - X_COL["B"], "C")
    hoja.campo(X_COL["B"], 13, "PARA:", jefe, X_FIN)
    hoja.texto(X_COL["B"], 14, "(NOMBRE DEL JEFE INMEDIATO GTC)", X_FIN - X_COL["B"], "C")
    hoja.campo(X_COL["G"], 15, "CODIGO:", codigo or "", X_FIN)
    hoja.campo(X_COL["B"], 16, "PUESTO:", puesto or "", X_COL["F"] - 3)
    hoja.campo(X_COL["G"], 16, "FECHA", fecha_doc, X_FIN)

    # --- Naturaleza de la acción --------------------------------------------
    _dibujar_marco(hoja)
    hoja.texto(X_COL["A"], 18, "NATURALEZA DE LA ACCION", X_FIN - X_COL["A"], "C")
    for fila, *opciones in CUADRICULA:
        for (col_casilla, col_texto), opcion in zip(_BLOQUES, opciones):
            if opcion is None:
                continue
            hoja.borde(col_casilla, fila, "lrtb")
            hoja.texto(X_COL[col_texto] + 0.8, fila, opcion)
            if opcion == tipo_ausencia:
                hoja.texto(X_COL[col_casilla], fila, "X", ANCHO_COL[col_casilla], "C", estilo="B")
    if tipo_ausencia and not any(tipo_ausencia in f for f in CUADRICULA):
        # Un motivo fuera de la plantilla se marca como OTROS con su nombre.
        hoja.texto(X_COL["H"], 30, "X", ANCHO_COL["H"], "C", estilo="B")
        hoja.texto(X_COL["I"] + 12, 32, f"({tipo_ausencia})", tamano=8)

    x_i = X_COL["I"] + 0.8
    hoja.texto(x_i, 36, "Del")
    x = x_i + hoja.ancho_texto("Del ") + 0.5
    for etiqueta, valor in (("", formato_fecha(fecha_inicio)), (" al ", formato_fecha(fecha_fin))):
        if etiqueta:
            hoja.texto(x, 36, etiqueta.strip())
            x += hoja.ancho_texto(etiqueta)
        ancho = 22
        base = Y_FILA[36] + ALTO_FILA[36] - 0.6
        hoja.linea(x, base, x + ancho, base)
        hoja.texto(x, 36, valor, ancho, "C", estilo="B")
        x += ancho
    hoja.campo(x_i, 38, "Cantidad de dias", str(dias), X_FIN - 6)

    # --- Explicación ----------------------------------------------------------
    hoja.texto(X_COL["B"], 39, "EXPLICACION DE LA ACCION")
    caja_x, caja_w = X_COL["B"], X_FIN - X_COL["B"] - 1.5
    caja_y = Y_FILA[40] + 0.5
    caja_h = Y_FILA[48] - caja_y - 0.5
    texto_exp = _latin1(explicacion)
    for tamano in (9, 8, 7):
        hoja.fuente(tamano)
        interlineado = tamano * MM_POR_PT * 1.25
        lineas = _contar_lineas(pdf, texto_exp, caja_w)
        if lineas * interlineado <= caja_h:
            break
    else:
        maximo = int(caja_h / interlineado)
        texto_exp = _recortar(pdf, texto_exp, caja_w, maximo)
    pdf.set_xy(caja_x, caja_y)
    pdf.multi_cell(caja_w, interlineado, texto_exp, 0, "L")
    hoja.texto(
        X_COL["B"], 48,
        "NOTA: ESTE FORMULARIO DEBE LLENARSE COMPLETO Y REMITIRLO INMEDIATAMENTE AL DEPARTAMENTO DE RR.HH.",
        X_FIN - X_COL["B"], "C",
    )

    # --- Firmas (líneas en la fila 51, títulos en la 52) ----------------------
    denegada = resolucion == "Denegada"
    firmo_banco = estado_workflow in (ESTADO_PENDIENTE_APROBACION_GERENCIA, ESTADO_FINALIZADA) and _tiene_firma(firma_jefe_b64)
    firmo_gerencia = estado_workflow == ESTADO_FINALIZADA and _tiene_firma(firma_gerencia_b64)
    hoja.fuente(9, "B")
    espacios = [
        (X_COL["C"], hoja.ancho_texto("_" * 25), firma_jefe_b64 if firmo_banco else None,
         "JEFE INMEDIATO GTC", jefe if firmo_banco else "(Pendiente)"),
        (X_COL["D"], hoja.ancho_texto("_" * 26), firma_empleado_b64,
         "EMPLEADO QUE SE LE APLICA", nombre_emp),
        (X_COL["I"], hoja.ancho_texto("_" * 32), firma_gerencia_b64 if firmo_gerencia else None,
         "SETESA",
         "Gerencia SETESA" if firmo_gerencia else "(No aplica)" if denegada else "(Pendiente)"),
    ]
    base_firmas = Y_FILA[51] + ALTO_FILA[51] - 0.8
    temporales = []
    try:
        for x, ancho, firma, titulo, nombre in espacios:
            if _tiene_firma(firma):
                ruta = base64_to_image(firma)
                if ruta and os.path.exists(ruta):
                    temporales.append(ruta)
                    w, h = min(42.0, ancho), min(42.0, ancho) / 3
                    pdf.image(ruta, x=x + (ancho - w) / 2, y=base_firmas - h - 0.5, w=w, h=h)
            hoja.linea(x, base_firmas, x + ancho, base_firmas)
            hoja.texto(x, 52, titulo, ancho, "C")
            hoja.texto(x, 53, nombre, ancho, "C", tamano=8)
    finally:
        for ruta in temporales:
            eliminar_archivo(ruta)

    # --- Resolución y pie -------------------------------------------------------
    y = Y_FILA[55]
    if resolucion:
        titulo = f"RESOLUCION: {resolucion.upper()}"
        if denegada and denegada_por:
            titulo += f" POR {denegada_por.upper()}"
        hoja.fuente(10, "B")
        pdf.set_xy(X_COL["B"], y)
        pdf.cell(X_FIN - X_COL["B"], 6, _latin1(titulo), 1, 1, "C")
        y += 6
        if denegada and motivo_resolucion:
            hoja.fuente(9)
            pdf.set_xy(X_COL["B"], y)
            pdf.multi_cell(X_FIN - X_COL["B"], 4.5, _latin1(f"Motivo: {motivo_resolucion}"), 1, "L")
            y = pdf.get_y()
    hoja.fuente(7)
    pdf.set_xy(X_COL["B"], max(y + 3, 280))
    pie = f"Expediente #{id_solicitud} - " if id_solicitud else ""
    pie += f"Estado: {estado_workflow} - Generado por SETESA Workflow el {datetime.date.today():%d/%m/%Y}"
    pdf.cell(X_FIN - X_COL["B"], 4, _latin1(pie), 0, 0, "C")

    # --- Archivo ----------------------------------------------------------------
    ensure_dirs()
    base = _segmento_archivo(nombre_emp)
    if id_solicitud:
        nombre_archivo = f"accion_{id_solicitud}_{base}_{dias}d.pdf"
    else:
        nombre_archivo = f"accion_{base}_{dias}d_{uuid4().hex[:8]}.pdf"
    destino = PDF_DIR / nombre_archivo
    temporal_pdf = PDF_DIR / f".tmp_{uuid4().hex}.pdf"
    try:
        pdf.output(str(temporal_pdf))
        os.replace(temporal_pdf, destino)
    finally:
        eliminar_archivo(temporal_pdf)
    return str(destino)


def _contar_lineas(pdf, texto, ancho):
    """Líneas que ocupará ``texto`` en multi_cell con la fuente actual."""
    total = 0
    for parrafo in texto.split("\n"):
        palabras, actual = parrafo.split(" "), ""
        total += 1
        for palabra in palabras:
            prueba = f"{actual} {palabra}".strip()
            if pdf.get_string_width(prueba) > ancho - 2 and actual:
                total += 1
                actual = palabra
            else:
                actual = prueba
    return total


def _recortar(pdf, texto, ancho, maximo):
    """Recorta el texto para que quepa en ``maximo`` líneas."""
    sufijo = " ... (texto completo en el sistema)"
    palabras = texto.split(" ")
    while palabras and _contar_lineas(pdf, " ".join(palabras) + sufijo, ancho) > maximo:
        palabras.pop()
    return " ".join(palabras) + sufijo
