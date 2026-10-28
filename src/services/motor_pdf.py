# Generación de documento oficial inalterable con FPDF.

import os
import re
import datetime
from uuid import uuid4

from fpdf import FPDF

from src.services.utils_firma import base64_to_image, eliminar_archivo
from src.core.config import PDF_DIR, ensure_dirs
from src.core.workflow import ESTADO_PENDIENTE_APROBACION_GERENCIA, ESTADO_FINALIZADA

def limpiar_nombre(nombre_crudo):
    """Elimina etiquetas como '(Consultor)' del nombre para estampar en la firma."""
    return nombre_crudo.split(" (")[0] if " (" in nombre_crudo else nombre_crudo

def _segmento_archivo(texto):
    """Convierte un texto en un segmento seguro para nombres de archivo."""
    limpio = re.sub(r"[^A-Za-z0-9_-]+", "_", texto).strip("_")
    return limpio or "empleado"

def _tiene_firma(firma_b64):
    return bool(firma_b64 and isinstance(firma_b64, str) and firma_b64.strip())

def generar_pdf_accion_personal(nombre_empleado, jefe_gtc, puesto, codigo, tipo_ausencia, fecha_inicio, fecha_fin, dias, explicacion, estado_workflow="Ingresada", fecha_creacion=None, firma_empleado_b64=None, firma_jefe_b64=None, firma_gerencia_b64=None, id_solicitud=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    nombre_emp_limpio = limpiar_nombre(nombre_empleado)
    jefe_limpio = limpiar_nombre(jefe_gtc)
    
    if not fecha_creacion:
        fecha_creacion = datetime.date.today().strftime("%Y-%m-%d")
    else:
        fecha_creacion = str(fecha_creacion).split()[0]
    
    # Encabezado
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 8, "SETESA", ln=True, align="C")
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 6, "ACCION DE PERSONAL", ln=True, align="C")
    pdf.ln(5)
    
    # Bloque 1: Datos Generales
    pdf.set_font("Arial", "", 10)
    pdf.cell(20, 6, "DE:", border=0)
    pdf.cell(100, 6, nombre_emp_limpio, border="B")
    pdf.cell(20, 6, "CODIGO:", border=0)
    pdf.cell(0, 6, codigo, border="B", ln=True)
    
    pdf.cell(20, 4, "", border=0)
    pdf.cell(100, 4, "(NOMBRE DEL EMPLEADO)", border=0, align="C")
    pdf.cell(0, 4, "", border=0, ln=True)
    
    pdf.cell(20, 6, "PARA:", border=0)
    pdf.cell(100, 6, jefe_limpio, border="B")
    pdf.cell(20, 6, "PUESTO:", border=0)
    pdf.cell(0, 6, puesto, border="B", ln=True)
    
    pdf.cell(20, 4, "", border=0)
    pdf.cell(100, 4, "(NOMBRE DEL JEFE INMEDIATO GTC)", border=0, align="C")
    pdf.cell(20, 6, "FECHA:", border=0)
    pdf.cell(0, 6, fecha_creacion, border="B", ln=True)
    pdf.ln(5)
    
    # Bloque 2: Cuadrícula de Naturaleza de la Acción
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "NATURALEZA DE LA ACCION", ln=True)
    pdf.set_font("Arial", "", 9)
    
    filas_opciones = [
        ["PERMISO CON GOCE DE SUELDO", "MATRIMONIO", "EVALUACION DEL DESEMPEÑO"],
        ["PERMISO SIN GOCE DE SUELDO", "RENUNCIA", "CALIFICACION DE MERITO"],
        ["LLEGADA TARDIA", "DESPIDO", "ASCENSO"],
        ["FALTA INJUSTIFICADA", "AMONESTACION VERBAL", "TRASLADO"],
        ["ABANDONO DE LABORES", "AMONESTACION ESCRITA", "NACIMIENTO DE HIJO (A)"],
        ["SUSPENSIÓN IGSS", "DESCONTAR SEPTIMO", "OTROS"],
        ["VACACION", "SUSPENSION", ""],
        ["DUELO", "CONTRATACION", ""]
    ]
    
    for fila in filas_opciones:
        check1 = "[ X ]" if fila[0] == tipo_ausencia else "[   ]"
        pdf.cell(65, 6, f"{check1} {fila[0]}" if fila[0] else "", border=0)
        
        check2 = "[ X ]" if fila[1] == tipo_ausencia else "[   ]"
        pdf.cell(65, 6, f"{check2} {fila[1]}" if fila[1] else "", border=0)
        
        check3 = "[ X ]" if fila[2] == tipo_ausencia else "[   ]"
        pdf.cell(60, 6, f"{check3} {fila[2]}" if fila[2] else "", border=0, ln=True)
        
    pdf.ln(5)
    
    # Bloque 3: Fechas
    pdf.cell(40, 6, f"Del  {fecha_inicio}", border=0)
    pdf.cell(40, 6, f"al  {fecha_fin}", border=0)
    pdf.cell(0, 6, f"Cantidad de dias  {dias}", border=0, ln=True)
    pdf.ln(5)
    
    # Bloque 4: Explicación
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "EXPLICACION DE LA ACCION", ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(0, 6, explicacion, border=1)
    pdf.ln(5)
    
    # Bloque 5: Nota Institucional
    pdf.set_font("Arial", "B", 8)
    pdf.multi_cell(0, 4, "NOTA: ESTE FORMULARIO DEBE LLENARSE COMPLETO Y REMITIRLO INMEDIATAMENTE AL DEPARTAMENTO DE RR.HH.")
    pdf.ln(12)
    
    # Bloque 6: Firmas Dinámicas según Workflow
    # La leyenda "(Pendiente Autorización)" solo se imprime cuando el estado aún
    # no autoriza esa firma o cuando falta la imagen (datos históricos).
    firma_emp = nombre_emp_limpio
    aprobado_coordinador = estado_workflow in (
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        ESTADO_FINALIZADA,
    )
    aprobado_gerencia = estado_workflow == ESTADO_FINALIZADA

    firma_jefe = (
        jefe_limpio
        if aprobado_coordinador and _tiene_firma(firma_jefe_b64)
        else "(Pendiente Autorización)"
    )
    firma_gerencia = (
        "Gerencia SETESA"
        if aprobado_gerencia and _tiene_firma(firma_gerencia_b64)
        else "(Pendiente Autorización)"
    )
    
    # Validar que quede espacio para las firmas en la página actual
    if pdf.get_y() > 240:
        pdf.add_page()
        
    y_firmas = pdf.get_y() + 5
    temporales = []

    def colocar_firma(b64_str, x_pos):
        if not _tiene_firma(b64_str):
            return
        img_path = base64_to_image(b64_str)
        if not img_path or not os.path.exists(img_path):
            return
        temporales.append(img_path)
        try:
            # Inyectamos la firma respetando la proporción 3:1 de utils_firma (45x15 mm)
            pdf.image(img_path, x=x_pos, y=y_firmas, w=45, h=15)
        except Exception as e:
            print(f"Error incrustando la firma en PDF: {e}")

    try:
        # --- CÁLCULO DE CENTRADO EXACTO ---
        # Centros teóricos de cada columna: Col 1 = 40mm, Col 2 = 100mm, Col 3 = 160mm.
        # Restamos la mitad del ancho de la imagen (45/2 = 22.5) para que quede 100% centrada
        colocar_firma(firma_jefe_b64, 17.5)
        colocar_firma(firma_empleado_b64, 77.5)
        colocar_firma(firma_gerencia_b64, 137.5)

        # Bajar el cursor 15mm (la altura exacta de la imagen) para dibujar las líneas
        pdf.set_y(y_firmas + 15)

        # Dibujo de líneas y nombres
        pdf.set_font("Arial", "", 9)
        pdf.cell(60, 5, "_________________________", ln=False, align="C")
        pdf.cell(60, 5, "_________________________", ln=False, align="C")
        pdf.cell(60, 5, "_________________________", ln=True, align="C")

        pdf.set_font("Arial", "B", 9)
        pdf.cell(60, 5, firma_jefe, ln=False, align="C")
        pdf.cell(60, 5, firma_emp, ln=False, align="C")
        pdf.cell(60, 5, firma_gerencia, ln=True, align="C")

        pdf.set_font("Arial", "", 9)
        pdf.cell(60, 5, "JEFE INMEDIATO GTC", ln=False, align="C")
        pdf.cell(60, 5, "EMPLEADO QUE SE LE APLICA", ln=False, align="C")
        pdf.cell(60, 5, "SETESA", ln=True, align="C")

        # Nombre determinista por expediente: evita sobrescrituras entre
        # solicitudes distintas y permite localizar el PDF oficial.
        ensure_dirs()
        base = _segmento_archivo(nombre_emp_limpio)
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
    finally:
        # H-15: no dejar imágenes temporales acumuladas en storage/firmas
        for ruta in temporales:
            eliminar_archivo(ruta)
