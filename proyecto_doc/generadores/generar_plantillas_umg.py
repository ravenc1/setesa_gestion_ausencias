# -*- coding: utf-8 -*-
"""
Genera "Plantillas_UMG_Completadas.docx" a partir de la plantilla oficial
"Plantillas_Implementacion_Solucion_Proyecto_Graduacion_II_UMG.docx",
rellenando todos los campos vacíos con información verificable del proyecto
"Digitalización y Automatización de Flujo de Solicitudes de Ausencia Laboral y
Gestión de Vigencia de Usuarios para la empresa SETESA".

Salida: proyecto_doc/plantillas_llenadas/Plantillas_UMG_Completadas.docx
"""

import re
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.oxml import OxmlElement

BASE = Path(r"C:\Users\conde\OneDrive\Documentos\UMG 2026\Segundo Semestre\PG2\proyecto_setesa")
PLANTILLA = BASE / "proyecto_doc" / "plantillas" / "Plantillas_Implementacion_Solucion_Proyecto_Graduacion_II_UMG.docx"
OUT_DIR = BASE / "proyecto_doc" / "plantillas_llenadas"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SALIDA = OUT_DIR / "Plantillas_UMG_Completadas.docx"
DIAGRAMA = OUT_DIR / "diagrama_procesos.png"

ESTUDIANTE = "Ricardo Andree Sebastián Arias Conde"
CARRERA = "Ingeniería en Sistemas de Información y Ciencias de la Computación"
TITULO = ("Digitalización y Automatización de Flujo de Solicitudes de Ausencia Laboral y "
          "Gestión de Vigencia de Usuarios para la empresa SETESA, zona 4, Guatemala")
FECHA = "Guatemala, noviembre de 2026"

REFLEXION = (
    "Se implementó una plataforma web (Python/Streamlit + PostgreSQL) que digitaliza el ciclo de vida "
    "de la \"Acción de Personal\", automatiza la generación del PDF oficial con firmas digitalizadas y "
    "ejecuta la depuración semestral de usuarios mediante baja lógica. La evidencia de su funcionamiento "
    "son los scripts de validación (auth.py, registro.py, motor_pdf.py, coordinador.py, vigencia.py, "
    "dashboard.py), los expedientes PDF almacenados en storage/pdf y los registros transaccionales en "
    "PostgreSQL. Permanece como limitación la no integración con los sistemas del banco (por ciberseguridad) "
    "y que el sistema no calcula nómina. Se recomienda como siguiente paso integrar reportes analíticos "
    "avanzados y extender el módulo de vigencia a notificaciones automatizadas."
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def iter_block_items(parent):
    for child in parent.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def set_cell(cell, text):
    """Escribe texto en una celda conservando el formato del primer run."""
    p = cell.paragraphs[0]
    # eliminar párrafos sobrantes
    for extra in cell.paragraphs[1:]:
        extra._element.getparent().remove(extra._element)
    if p.runs:
        p.runs[0].text = text
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.add_run(text)


def fill_table(table, rows_data, start_row=1, start_col=0):
    """Rellena filas de datos de una tabla (por defecto desde la fila 1)."""
    for i, row_data in enumerate(rows_data):
        r = start_row + i
        if r >= len(table.rows):
            break
        for j, value in enumerate(row_data):
            if value is None:
                continue
            c = start_col + j
            if c < len(table.columns):
                set_cell(table.rows[r].cells[c], value)


def answer_underscores(paragraph, text):
    """Sustituye la primera línea de guiones bajos por la respuesta y descarta
    las líneas de guiones restantes (bloques multilínea) para no duplicar texto."""
    full = paragraph.text
    if not re.search(r"_{3,}", full):
        paragraph.add_run(text)
        return
    lineas = full.split("\n")
    salida, reemplazado = [], False
    for linea in lineas:
        if re.search(r"_{3,}", linea):
            if not reemplazado:
                salida.append(re.sub(r"_{3,}", text, linea))
                reemplazado = True
            # las demás líneas de guiones se descartan
        else:
            salida.append(linea)
    paragraph.clear()
    paragraph.add_run("\n".join(salida))


def insert_image_after(paragraph, image_path, width_inches=6.2):
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    run = new_para.add_run()
    run.add_picture(str(image_path), width=Inches(width_inches))
    return new_para


# ---------------------------------------------------------------------------
# Contenido de las tablas
# ---------------------------------------------------------------------------
TABLA_1_RESUMEN = [
    ("Sistema web \"SETESA Workflow\" – Plataforma de Gestión de Ausencias y Vigencia de Usuarios",),
    ("Proceso manual y descentralizado de \"Acción de Personal\" (Excel y correos); pérdida de "
     "trazabilidad documental, entre 4 y 6 horas mensuales de depuración manual de usuarios y riesgo "
     "de inconsistencias en el cálculo de nómina.",),
    ("Implementar una plataforma web centralizada (Python/Streamlit + PostgreSQL) que digitalice el ciclo "
     "de vida de las solicitudes de ausencia, automatice la generación del PDF oficial y ejecute la "
     "depuración semestral de vigencia de usuarios.",),
    ("Arquitectura web monolítica modular de tres capas: capa de presentación reactiva en Streamlit "
     "(streamlit-drawable-canvas), capa de lógica de negocio en Python/Pandas con workflow de estados y "
     "motor FPDF, y capa de datos en PostgreSQL con seguridad RBAC y baja lógica.",),
    ("Consultores técnicos (solicitantes), Coordinador GTC del cliente/banco (revisor), Gerencia General "
     "de SETESA (aprobador), Departamento de Contabilidad (usuario administrativo) y Administrador de TI/"
     "Investigador (soporte).",),
    ("Gestión de usuarios con RBAC; módulo de solicitudes; workflow de aprobación trazable; automatización "
     "documental con generación de PDF; algoritmo de vigencia semestral; dashboard administrativo con KPIs; "
     "y captura de firmas digitalizadas (Canvas/Base64).",),
    ("Integración directa con los sistemas y bases de datos del banco (cliente); cálculo automático de "
     "salarios o nómina (no es software contable); adaptación a leyes laborales extranjeras; y uso de "
     "hardware biométrico o tabletas de captura externas.",),
    ("Entorno cloud de pruebas y despliegue real autorizado por SETESA (Supabase como DBaaS y Render "
     "como PaaS), independiente de la infraestructura tecnológica del cliente bancario.",),
    ("24 semanas (aproximadamente 6 meses), comprendidas entre las fases de análisis, diseño, desarrollo, "
     "aseguramiento de calidad y despliegue, con cierre formal en noviembre de 2026.",),
]

TABLA_2_PLAN = [
    ("1", "Análisis y levantamiento de requerimientos (entrevistas, formato oficial, DER y casos de uso)",
     "Investigador / Gerencia SETESA", "Entrevistas, Lucidchart", "Semana 1", "Semana 4", "Completado"),
    ("2", "Diseño de la arquitectura y del esquema de base de datos PostgreSQL (usuario, rol, solicitud)",
     "Investigador", "PostgreSQL, VS Code", "Semana 5", "Semana 8", "Completado"),
    ("3", "Desarrollo del módulo de autenticación y gestión de perfiles (RBAC)",
     "Investigador", "Python, Streamlit", "Semana 9", "Semana 10", "Completado"),
    ("4", "Implementación del formulario inteligente de solicitudes y carga de evidencias",
     "Investigador", "Python, Streamlit, Pandas", "Semana 11", "Semana 12", "Completado"),
    ("5", "Programación del motor de generación de PDF (FPDF) y del flujo de notificaciones",
     "Investigador", "Python, FPDF", "Semana 13", "Semana 14", "Completado"),
    ("6", "Desarrollo del algoritmo de vigencia para la depuración semestral de usuarios inactivos",
     "Investigador", "SQL, PostgreSQL, triggers", "Semana 15", "Semana 16", "Completado"),
    ("7", "Pruebas unitarias, de caja negra, corrección de errores y UAT",
     "Investigador / Consultores SETESA", "Scripts de prueba, PostgreSQL", "Semana 17", "Semana 20", "En proceso"),
    ("8", "Despliegue en producción cloud, capacitación al personal y entrega formal del proyecto",
     "Investigador / Gerencia", "Supabase/Render, manuales", "Semana 21", "Semana 24", "Pendiente"),
]

TABLA_3_RECURSOS = [
    ("Humanos", "Investigador/Desarrollador, Asesor de tesis, Stakeholders de SETESA y Consultores técnicos",
     "1 investigador, 1 asesor, Gerencia, Contabilidad y 15 colaboradores de muestra", "Alta disponibilidad",
     "Ejecutan el desarrollo, la validación metodológica y la prueba de usuario final."),
    ("Tecnológicos", "Python 3.13, Streamlit, PostgreSQL y Pandas",
     "1 entorno de desarrollo y 1 servidor cloud", "100 % Open Source",
     "Stack principal del sistema y de la capa de datos."),
    ("Software / licencias", "Visual Studio Code, Git/GitHub, Lucidchart y FPDF",
     "1 instancia por herramienta", "Gratuito / Open Source",
     "IDE, control de versiones, diagramación y motor de documentos."),
    ("Infraestructura", "Supabase (DBaaS) y Render (PaaS)",
     "1 instancia cloud escalable con respaldos automáticos", "$25 – $35 USD mensuales",
     "Garantiza alta disponibilidad e independencia del banco."),
    ("Financieros", "Hosting cloud, gastos administrativos y capacitación",
     "Presupuesto operativo del proyecto", "Inversión mínima (tecnologías Open Source)",
     "El retorno se refleja en la reducción de horas-hombre de depuración."),
    ("Materiales / datos", "Formato oficial \"Acción de Personal\", manuales de puestos y listados históricos de usuarios",
     "Documentación institucional de SETESA", "100 % proporcionado por SETESA",
     "Insumos para el diseño de la base de datos y la migración."),
]

TABLA_4_PROCESO = [
    ("1. Preparación", "Requerimientos y formato oficial de \"Acción de Personal\"",
     "Levantamiento de requerimientos, definición de reglas de negocio y diseño del DER",
     "DER y casos de uso aprobados", "Documento validado y firmado por la Gerencia de SETESA"),
    ("2. Configuración / desarrollo", "DER y diseño del esquema de base de datos",
     "Desarrollo de los módulos RBAC, formulario de solicitudes, motor FPDF y algoritmo de vigencia",
     "Sistema funcional modular en Streamlit", "Módulos operativos y probados de forma incremental"),
    ("3. Pruebas", "Sistema desarrollado y datos de prueba",
     "Pruebas unitarias de BD, pruebas de caja negra y pruebas de aceptación (UAT)",
     "Informe de QA con correcciones aplicadas", "Todos los casos PR-01 a PR-06 aprobados"),
    ("4. Implementación / piloto", "Sistema probado",
     "Despliegue en la nube y piloto con un grupo de control de consultores",
     "Sistema en producción autorizado", "Operación sin pérdida de datos ni solicitudes huérfanas"),
    ("5. Seguimiento", "Sistema en producción",
     "Monitoreo de KPIs, auditoría de trazabilidad y ejecución del algoritmo de vigencia",
     "Reportes de auditoría y métricas de eficiencia", "Reducción verificada del tiempo de procesamiento"),
]

TABLA_5_REQUISITOS = [
    ("R-01", "RF-01 Autenticación y control de acceso basado en roles (RBAC)",
     "Alta", "Módulo auth.py",
     "El login enruta por rol y bloquea a usuarios con estado_vigencia = FALSE", "Completado"),
    ("R-02", "RF-02 Registro de solicitudes de ausencia con validación en tiempo real",
     "Alta", "Formulario registro.py",
     "La solicitud se registra en PostgreSQL y calcula días hábiles en menos de 5 minutos", "Completado"),
    ("R-03", "RF-03 Generación automática del PDF oficial de \"Acción de Personal\"",
     "Alta", "Módulo motor_pdf.py",
     "El PDF es fiel a la plantilla oficial de SETESA con datos inyectados y firmas", "Completado"),
    ("R-04", "RF-04 Workflow trazable y dashboard administrativo con filtros",
     "Media", "Módulos dashboard.py y coordinador.py",
     "Los estados del workflow y los KPIs se visualizan en tiempo real", "En proceso"),
    ("R-05", "RF-05 Algoritmo de vigencia semestral con baja lógica",
     "Alta", "Módulo vigencia.py",
     "estado_vigencia cambia a FALSE tras 6 meses sin actividad, sin borrar el historial", "Completado"),
    ("R-06", "RF-06 Captura de firma manuscrita (Canvas/Base64) incrustada en el PDF",
     "Alta", "Módulo utils_firma.py",
     "La firma se captura, codifica en Base64 y se estampa en el PDF según el estado", "Completado"),
]

TABLA_6_PRUEBAS = [
    ("PR-01", "Login y RBAC", "Usuario activo e inactivo registrado en la tabla usuario",
     "El sistema enruta la interfaz por rol y bloquea al usuario inactivo",
     "Verificado en auth.py / app.py", "Capturas de pantalla", "Completado"),
    ("PR-02", "Cálculo y registro de solicitud", "Fechas de ausencia válidas en el formulario",
     "El sistema calcula días hábiles e inserta el registro en PostgreSQL",
     "Verificado en registro.py", "Registro en base de datos", "Completado"),
    ("PR-03", "Generación del motor PDF", "Solicitud registrada en estado inicial",
     "FPDF genera el PDF oficial con los datos inyectados",
     "Verificado en motor_pdf.py", "Archivo PDF generado", "Completado"),
    ("PR-04", "Aprobación externa (Banco)", "Solicitud pendiente de visto bueno del coordinador",
     "UPDATE del estado a \"Pendiente de Aprobación Gerencia\"",
     "Verificado en coordinador.py", "Historial de estados", "Completado"),
    ("PR-05", "Algoritmo de baja lógica", "Usuario con más de 6 meses sin actividad (ultima_actividad)",
     "estado_vigencia = FALSE conservando el historial para auditoría",
     "Verificado en vigencia.py", "Consulta SQL de validación", "Completado"),
    ("PR-06", "Captura e incrustación de firma", "Lienzo Canvas en el panel operativo",
     "El trazo se codifica en Base64 y se estampa en el PDF según el estado",
     "En proceso en utils_firma.py", "Imagen PNG / PDF firmado", "En proceso"),
]

TABLA_7_RESULTADOS = [
    ("Tiempo de procesamiento por solicitud", "30 – 45 minutos (proceso manual)",
     "Menos de 5 minutos", "Menos de 5 minutos en el prototipo",
     "Logs de fecha_creacion en PostgreSQL", "Reducción superior al 85 % del tiempo operativo"),
    ("Horas de depuración manual de usuarios inactivos", "4 – 6 horas mensuales",
     "0 horas (automatizado)", "Ejecución del algoritmo en milisegundos",
     "Ejecución de vigencia.py / consultas SQL", "Automatización total de la depuración"),
    ("Pérdida de trazabilidad documental", "60 % de incidentes reportados",
     "0 % de pérdida", "0 % en el repositorio PostgreSQL",
     "Integridad referencial de la base de datos", "Expedientes persistentes y auditables"),
    ("Precisión del padrón de usuarios activos", "Depuración manual propensa a error",
     "100 % de usuarios activos", "100 % mediante baja lógica",
     "Consultas SQL de validación", "Gobernanza efectiva de los datos de personal"),
    ("Percepción de eficiencia del proceso", "73.3 % lo consideraba ineficiente",
     "Más de 90 % de satisfacción", "Pendiente de encuesta post-implementación",
     "Encuesta con escala de Likert", "Validación de la aceptación del usuario final"),
]

TABLA_8_SEGUIMIENTO = [
    ("Disponibilidad del sistema", "Monitoreo del servicio cloud y revisión de logs",
     "Continua", "Administrador de TI", "Reinicio del servicio o escalamiento a soporte cloud"),
    ("Tiempo promedio de aprobación de solicitudes", "Logs de fecha_creacion por estado del workflow",
     "Mensual", "Gerencia General", "Revisión del workflow y de los tiempos del coordinador del banco"),
    ("Precisión de la depuración (baja lógica)", "Consultas SQL de validación sobre la tabla usuario",
     "Semestral", "Administrador de TI", "Reejecución del algoritmo de vigencia"),
    ("Integridad transaccional (solicitudes huérfanas)", "Verificación de propiedades ACID y claves foráneas",
     "Trimestral", "Administrador de TI", "Corrección de integridad referencial en PostgreSQL"),
    ("Satisfacción y usabilidad", "Encuesta con escala de Likert a consultores y gerencia",
     "Semestral", "Gerencia / Asesor", "Ajustes de interfaz y refuerzo de capacitación"),
]

TABLA_9_RIESGOS = [
    ("2026-02", "Resistencia al cambio del personal acostumbrado al correo electrónico",
     "Media / Alto", "Capacitación y manuales de usuario",
     "Investigador / Gerencia", "Cerrado"),
    ("Semana 5", "Restricciones de ciberseguridad del cliente (banco) para integrar sistemas",
     "Alta / Medio", "Independencia arquitectónica y firma mediante PDF",
     "Investigador", "Cerrado"),
    ("Semana 12", "Curva de aprendizaje técnica durante el despliegue",
     "Media / Medio", "Documentación técnica y acompañamiento",
     "Investigador", "Cerrado"),
    ("Semana 18", "Errores (bugs) detectados en las pruebas de caja negra",
     "Media / Alto", "Corrección de errores y optimización de tiempos de carga",
     "Investigador", "Cerrado"),
    ("Semana 21", "Retrasos por validación de requerimientos con el cliente",
     "Baja / Medio", "Margen de contingencia dentro del cronograma ágil",
     "Gerencia", "Abierto"),
]

TABLA_10_EVIDENCIAS = [
    ("Ubicación de evidencias", "Repositorio GitHub del proyecto y carpeta storage/ (subcarpetas pdf y firmas)"),
    ("Convención de nombres", "PR-0X_caso-prueba_fecha y accion_<usuario>_<id>d.pdf"),
    ("Responsable de custodia", "Ricardo A. S. Arias Conde (Investigador) / Administrador de TI de SETESA"),
    ("Restricciones de acceso", "Acceso restringido por RBAC; los datos sensibles solo los visualiza Gerencia"),
]

TEXTOS_ANALISIS = {
    "2. Plan de trabajo": (
        "Dependencias: el diseño de la base de datos depende del DER; el motor PDF depende del módulo de "
        "registro; las pruebas UAT dependen del despliegue. Riesgo de calendario: la validación de "
        "requerimientos con el cliente puede extender el cronograma; medida de contingencia: desarrollo "
        "ágil por incrementos y un margen de holgura en las últimas semanas."),
    "6. Plan de pruebas": (
        "La solución se aceptará cuando todos los casos de prueba PR-01 a PR-06 se completen con evidencia, "
        "el sistema opere en producción sin pérdida de datos, el workflow refleje los estados definidos y "
        "la Gerencia de SETESA valide el funcionamiento del PDF oficial de \"Acción de Personal\"."),
    "7. Resultados esperados": (
        "Comparación antes/después del proceso: la línea base (proceso manual) se contrasta con los "
        "resultados del sistema automatizado, empleando el tiempo de procesamiento, las horas de "
        "depuración manual y el porcentaje de incidentes de trazabilidad como variables de medición."),
    "11. Exposición de resultados": (
        "Preguntas previsibles: ¿cómo garantiza el sistema la validez legal de la firma? (Decreto 47-2008 y "
        "firma electrónica simple con RBAC); ¿cómo se protege la información sensible? (RBAC y Base64); "
        "¿cómo se evita la acumulación de usuarios inactivos? (algoritmo de vigencia con baja lógica)."),
}


def main() -> None:
    doc = Document(str(PLANTILLA))
    blocks = list(iter_block_items(doc))

    # ------------------------------------------------------------------
    # 1) Rellenar párrafos (portada, análisis y reflexión) y detectar
    #    el punto donde insertar el diagrama.
    # ------------------------------------------------------------------
    current_section = ""
    diagram_anchor = None
    secciones_respondidas = set()

    for blk in blocks:
        if not isinstance(blk, Paragraph):
            continue

        text = blk.text.strip()

        if blk.style.name.startswith("Heading 1"):
            current_section = text
            continue

        # Portada
        if text.startswith("Estudiante:"):
            blk.clear()
            lineas = [
                f"Estudiante: {ESTUDIANTE}",
                f"Carrera: {CARRERA}",
                f"Título del proyecto: {TITULO}",
                f"Fecha: {FECHA}",
            ]
            for i, linea in enumerate(lineas):
                run = blk.add_run(linea)
                if i < len(lineas) - 1:
                    run.add_break()
            continue

        # Ancla del diagrama (sección 4)
        if text.startswith("Espacio para insertar diagrama"):
            for run in blk.runs:
                if re.search(r"_{3,}", run.text):
                    run.text = re.sub(r"_{3,}", "diagrama_procesos.png (ver imagen adjunta)", run.text)
                    break
            diagram_anchor = blk
            continue

        # Párrafos de análisis con guiones bajos (una respuesta por sección)
        for clave, respuesta in TEXTOS_ANALISIS.items():
            if (current_section.startswith(clave) and clave not in secciones_respondidas
                    and re.search(r"_{3,}", text)):
                answer_underscores(blk, respuesta)
                secciones_respondidas.add(clave)
                break

        # Reflexión final
        if (current_section.startswith("Reflexión final")
                and "Reflexión final" not in secciones_respondidas
                and re.search(r"_{3,}", text)):
            answer_underscores(blk, REFLEXION)
            secciones_respondidas.add("Reflexión final")

    # ------------------------------------------------------------------
    # 2) Rellenar tablas
    # ------------------------------------------------------------------
    tablas = [b for b in blocks if isinstance(b, Table)]

    fill_table(tablas[0], TABLA_1_RESUMEN, start_row=0, start_col=1)   # 1. Resumen
    fill_table(tablas[1], TABLA_2_PLAN)             # 2. Plan de trabajo
    fill_table(tablas[2], TABLA_3_RECURSOS)         # 3. Recursos
    fill_table(tablas[3], TABLA_4_PROCESO)          # 4. Diseño del proceso
    fill_table(tablas[4], TABLA_5_REQUISITOS)       # 5. Requisitos
    fill_table(tablas[5], TABLA_6_PRUEBAS)          # 6. Plan de pruebas
    fill_table(tablas[6], TABLA_7_RESULTADOS)       # 7. Resultados
    fill_table(tablas[7], TABLA_8_SEGUIMIENTO)      # 8. Seguimiento
    fill_table(tablas[8], TABLA_9_RIESGOS)          # 9. Riesgos
    # Tabla 10 (evidencias): columnas Ubicación / Descripción
    for i, (etiqueta, valor) in enumerate(TABLA_10_EVIDENCIAS):
        set_cell(tablas[9].rows[i].cells[0], etiqueta)
        set_cell(tablas[9].rows[i].cells[1], valor)

    # ------------------------------------------------------------------
    # 3) Insertar el diagrama de procesos generado con Graphviz
    # ------------------------------------------------------------------
    if diagram_anchor is not None and DIAGRAMA.exists():
        insert_image_after(diagram_anchor, DIAGRAMA, width_inches=6.2)

    doc.save(str(SALIDA))
    print("Documento generado:", SALIDA)


if __name__ == "__main__":
    main()
