# -*- coding: utf-8 -*-
"""
Genera "Plantillas_Imagen_Completadas.docx" recreando las 8 plantillas de la
imagen "Implementación de la Solución_ Plantillas Universitarias.png",
rellenadas con la información técnica del proyecto SETESA e insertando el
diagrama de procesos (Plantilla 4) generado con Graphviz.

Salida: proyecto_doc/plantillas_llenadas/Plantillas_Imagen_Completadas.docx
"""

from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = Path(r"C:\Users\conde\OneDrive\Documentos\UMG 2026\Segundo Semestre\PG2\proyecto_setesa")
OUT_DIR = BASE / "proyecto_doc" / "plantillas_llenadas"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SALIDA = OUT_DIR / "Plantillas_Imagen_Completadas.docx"
DIAGRAMA = OUT_DIR / "diagrama_procesos.png"

AZUL = "1F6FB2"
AZUL_CLARO = "D6E6F4"
GRIS = "F2F2F2"


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------
def sombrear(celda, color_hex):
    tcPr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)


def escribir(celda, texto, negrita=False, color=None, size=9.5):
    celda.text = ""
    p = celda.paragraphs[0]
    run = p.add_run(texto)
    run.bold = negrita
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def titulo_plantilla(doc, numero, nombre, descripcion):
    p = doc.add_paragraph()
    run = p.add_run(f"PLANTILLA {numero}.  {nombre}")
    run.bold = True
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor.from_string(AZUL)
    d = doc.add_paragraph()
    run = d.add_run(descripcion)
    run.italic = True
    run.font.size = Pt(9.5)
    d.paragraph_format.space_after = Pt(6)


def tabla(doc, filas, encabezado=None):
    ncols = len(filas[0])
    t = doc.add_table(rows=0, cols=ncols)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    if encabezado:
        fila = t.add_row().cells
        for i, h in enumerate(encabezado):
            sombrear(fila[i], AZUL)
            escribir(fila[i], h, negrita=True, color="FFFFFF")
    for datos in filas:
        fila = t.add_row().cells
        for i, valor in enumerate(datos):
            escribir(fila[i], valor)
    return t


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------
def main() -> None:
    doc = Document()
    est = doc.styles["Normal"]
    est.font.name = "Calibri"
    est.font.size = Pt(10)

    # -------------------- Encabezado general --------------------
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("UNIVERSIDAD MARIANO GÁLVEZ DE GUATEMALA\n")
    r.bold = True
    r.font.size = Pt(12)
    r = p.add_run("Implementación de la Solución — Plantillas para el Proyecto de Graduación II")
    r.bold = True
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor.from_string(AZUL)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(
        "Proyecto: Digitalización y Automatización de Flujo de Solicitudes de Ausencia Laboral y "
        "Gestión de Vigencia de Usuarios para la empresa SETESA (zona 4, Guatemala)\n"
        "Estudiante: Ricardo Andree Sebastián Arias Conde  |  Curso: Proyecto de Graduación II  |  "
        "Catedrático: Msc. Ing. César Rodríguez Minas  |  Guatemala, noviembre de 2026"
    )
    r.font.size = Pt(9)

    # ==================== PLANTILLA 1 ====================
    doc.add_paragraph()
    titulo_plantilla(doc, 1, "RESUMEN DE LA IMPLEMENTACIÓN",
                     "Describe de forma general cómo se llevará a cabo la implementación de la solución propuesta.")
    tabla(doc, [
        ("Nombre de la solución",
         "Sistema web \"SETESA Workflow\" – Plataforma de Gestión de Ausencias y Vigencia de Usuarios."),
        ("Objetivo de la implementación",
         "Implementar un sistema web automatizado para digitalizar las solicitudes de ausencia laboral y "
         "controlar la vigencia de usuarios en SETESA, centralizando la información administrativa y "
         "garantizando el cumplimiento de las políticas de reporte interno."),
        ("Alcance",
         "Gestión de usuarios con RBAC; módulo de solicitudes (vacaciones, luto, suspensiones y permisos "
         "especiales); workflow de aprobación trazable; generación automática del PDF oficial \"Acción de "
         "Personal\"; algoritmo de vigencia semestral con baja lógica; dashboard administrativo con KPIs; y "
         "captura de firmas digitalizadas mediante lienzo Canvas (Base64)."),
        ("Responsables",
         "Investigador: Ricardo Andree Sebastián Arias Conde (análisis, diseño, desarrollo y pruebas). "
         "Gerencia General de SETESA (validación de procesos). Coordinador GTC y Departamento de "
         "Contabilidad (usuarios clave). Asesor de tesis (acompañamiento metodológico)."),
        ("Período de ejecución",
         "24 semanas (aproximadamente 6 meses), de enero a noviembre de 2026. Despliegue en producción y "
         "cierre formal en noviembre de 2026."),
    ])
    doc.add_page_break()

    # ==================== PLANTILLA 2 ====================
    titulo_plantilla(doc, 2, "PLAN DE TRABAJO DE LA IMPLEMENTACIÓN",
                     "Detalla las actividades, recursos y cronograma para llevar a cabo la implementación de la solución.")
    tabla(doc, [
        ("1", "Análisis y levantamiento de requerimientos (entrevistas, formato oficial, DER y casos de uso)",
         "Investigador / Gerencia", "Lucidchart, entrevistas", "Semana 1", "Semana 4"),
        ("2", "Diseño de la arquitectura y del esquema de base de datos PostgreSQL",
         "Investigador", "PostgreSQL, VS Code", "Semana 5", "Semana 8"),
        ("3", "Desarrollo del módulo de autenticación y gestión de perfiles (RBAC)",
         "Investigador", "Python, Streamlit", "Semana 9", "Semana 10"),
        ("4", "Implementación del formulario de solicitudes y carga de evidencias",
         "Investigador", "Python, Streamlit, Pandas", "Semana 11", "Semana 12"),
        ("5", "Programación del motor de generación de PDF (FPDF) y flujo de notificaciones",
         "Investigador", "Python, FPDF", "Semana 13", "Semana 14"),
        ("6", "Desarrollo del algoritmo de vigencia (depuración semestral y baja lógica)",
         "Investigador", "SQL, PostgreSQL, triggers", "Semana 15", "Semana 16"),
        ("7", "Pruebas unitarias, de caja negra, corrección de errores y UAT",
         "Investigador / Consultores", "Scripts de prueba, PostgreSQL", "Semana 17", "Semana 20"),
        ("8", "Despliegue en producción cloud, capacitación y entrega formal",
         "Investigador / Gerencia", "Supabase/Render, manuales", "Semana 21", "Semana 24"),
    ], encabezado=["No.", "Actividad", "Responsable", "Recursos necesarios", "Fecha de inicio", "Fecha de fin"])
    doc.add_page_break()

    # ==================== PLANTILLA 3 ====================
    titulo_plantilla(doc, 3, "RECURSOS",
                     "Identifica los recursos que necesitarás para la implementación de la solución.")
    tabla(doc, [
        ("Humanos",
         "Investigador/Desarrollador (análisis, diseño, codificación y pruebas); Asesor de tesis "
         "(acompañamiento metodológico y técnico); Gerencia General y Departamento de Contabilidad de "
         "SETESA (validación); Consultores técnicos (usuarios finales, muestra de 15 colaboradores)."),
        ("Tecnológicos",
         "Python 3.13 y Streamlit (con streamlit-drawable-canvas); PostgreSQL alojado en Supabase; FPDF y "
         "Pandas; Visual Studio Code como IDE; Git/GitHub para control de versiones; Lucidchart para "
         "diagramación."),
        ("Financieros",
         "Infraestructura cloud (Supabase DBaaS / Render PaaS) estimada en $25 – $35 USD mensuales; gastos "
         "administrativos (papelería, impresiones y trámites universitarios); horas-hombre de capacitación. "
         "El software es 100 % Open Source, sin costo de licencias."),
        ("Materiales",
         "Formato oficial preimpreso de \"Acción de Personal\"; manuales de puestos e instructivos internos "
         "de vacaciones; listados históricos de cuentas de usuario; equipo de cómputo de alto rendimiento y "
         "conexión a internet de banda ancha."),
    ], encabezado=["Categoría", "Recursos y descripción"])
    doc.add_page_break()

    # ==================== PLANTILLA 4 (con diagrama) ====================
    titulo_plantilla(doc, 4, "DIAGRAMA DE PROCESO DE IMPLEMENTACIÓN",
                     "Representa de forma gráfica los pasos principales para la implementación de la solución.")
    p = doc.add_paragraph()
    r = p.add_run(
        "El proceso de implementación del sistema SETESA se estructura en cinco fases secuenciales, alineadas "
        "con el cronograma de 24 semanas del proyecto:"
    )
    r.font.size = Pt(9.5)
    for fase in [
        "1. Planificación — Análisis y levantamiento de requerimientos, definición de reglas de negocio y DER (semanas 1–4).",
        "2. Desarrollo — Diseño de la base de datos PostgreSQL y codificación de los módulos RBAC, registro, motor FPDF y vigencia (semanas 5–16).",
        "3. Pruebas — QA: pruebas unitarias, de caja negra, corrección de errores y UAT (semanas 17–20).",
        "4. Despliegue — Puesta en marcha en la nube, respaldos y capacitación al personal (semanas 21–23).",
        "5. Seguimiento — Monitoreo de KPIs, auditoría de trazabilidad y algoritmo de vigencia semestral (semana 24 en adelante).",
    ]:
        par = doc.add_paragraph(style="List Bullet")
        run = par.add_run(fase)
        run.font.size = Pt(9.5)

    if DIAGRAMA.exists():
        pimg = doc.add_paragraph()
        pimg.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pimg.add_run().add_picture(str(DIAGRAMA), width=Inches(6.4))
        pie = doc.add_paragraph()
        pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pr = pie.add_run("Figura. Diagrama de Proceso de Implementación — elaboración propia (Graphviz).")
        pr.italic = True
        pr.font.size = Pt(8.5)
    doc.add_page_break()

    # ==================== PLANTILLA 5 ====================
    titulo_plantilla(doc, 5, "RESULTADOS ESPERADOS",
                     "Define qué resultados se esperan obtener con la implementación de la solución.")
    tabla(doc, [
        ("Técnicos",
         "Generación automática del PDF oficial \"Acción de Personal\" en menos de 5 minutos; integridad "
         "transaccional (ACID) en PostgreSQL; arquitectura web de tres capas (Streamlit / Python / "
         "PostgreSQL) desplegada en la nube; workflow con estados trazables (Ingresada, Pendiente de Firma "
         "Coordinador, Pendiente de Aprobación Gerencia, Finalizada)."),
        ("Operativos",
         "Reducción del tiempo por solicitud de 30–45 minutos a menos de 5 minutos; eliminación de las 4–6 "
         "horas mensuales de depuración manual de usuarios; erradicación del extravío de documentos y del "
         "\"bypass administrativo\" en las aprobaciones."),
        ("Académicos",
         "Aplicación de la ingeniería de requerimientos, la metodología ágil (Scrum/prototipado) y el "
         "estándar de calidad ISO/IEC 25010; evidencia documental (matrices de trazabilidad y pruebas) que "
         "respalda el trabajo de graduación."),
        ("Impacto",
         "Centralización y gobernanza del capital humano externo; fuente de verdad confiable para el área de "
         "Contabilidad; cumplimiento del Código de Trabajo (Decreto 1441) y de la Ley de Firmas Electrónicas "
         "(Decreto 47-2008)."),
    ], encabezado=["Tipo de resultado", "Descripción"])
    doc.add_page_break()

    # ==================== PLANTILLA 6 ====================
    titulo_plantilla(doc, 6, "EXPOSICIÓN DE RESULTADOS",
                     "Prepara una presentación clara y estructurada de los resultados esperados en la implementación de la solución.")
    tabla(doc, [
        ("1. Introducción (contexto y objetivo)",
         "Problema actual: proceso manual con Excel y correos; el 73.3 % del personal lo considera ineficiente "
         "y existe un 60 % de incidentes de trazabilidad. Objetivo: digitalizar el ciclo de vida de la "
         "\"Acción de Personal\" y automatizar la vigencia de usuarios."),
        ("2. Descripción de la solución implementada",
         "Arquitectura de tres capas (Streamlit / Python / PostgreSQL) con módulos de autenticación RBAC, "
         "registro de solicitudes, motor FPDF, coordinación GTC, algoritmo de vigencia, dashboard y captura "
         "de firmas mediante lienzo Canvas (Base64)."),
        ("3. Resultados esperados (con datos o proyecciones)",
         "Menos de 5 minutos por solicitud; 0 horas de depuración manual; 0 % de pérdida documental; 100 % "
         "del padrón de usuarios activo mediante baja lógica; trazabilidad total de los estados del workflow."),
        ("4. Conclusiones y recomendaciones",
         "La hipótesis se valida: el sistema optimiza el control administrativo y reduce el error humano. Se "
         "recomienda integrar reportes analíticos avanzados y notificaciones automáticas de vigencia."),
        ("5. Preguntas / retroalimentación",
         "¿Cómo se garantiza la validez legal de la firma? (Decreto 47-2008 y firma electrónica simple con "
         "RBAC). ¿Cómo se protege la información sensible? (RBAC y codificación Base64). ¿Cómo se evita la "
         "acumulación de usuarios inactivos? (algoritmo de vigencia con baja lógica)."),
    ])
    p = doc.add_paragraph()
    r = p.add_run("Consejo: "); r.bold = True; r.font.size = Pt(9.5)
    r = p.add_run("utilizar recursos visuales (el diagrama de proceso, tablas y el dashboard con KPIs) para "
                  "facilitar la comprensión de la presentación.")
    r.font.size = Pt(9.5)
    doc.add_page_break()

    # ==================== PLANTILLA 7 ====================
    titulo_plantilla(doc, 7, "SEGUIMIENTO Y MONITOREO",
                     "Establece cómo se dará el seguimiento a la implementación y cómo se evaluarán los resultados.")
    tabla(doc, [
        ("Tiempo de procesamiento por solicitud",
         "Logs del sistema y tabla solicitud (PostgreSQL, campo fecha_creacion)",
         "Mensual", "Gerencia General"),
        ("Precisión de la depuración (baja lógica)",
         "Tabla usuario (PostgreSQL) y Dashboard administrativo",
         "Semestral", "Administrador de TI"),
        ("Disponibilidad del sistema",
         "Servicio cloud (Supabase/Render) y revisión de logs",
         "Continua", "Administrador de TI"),
        ("Integridad transaccional (solicitudes huérfanas)",
         "Consultas SQL de validación en PostgreSQL",
         "Trimestral", "Administrador de TI"),
        ("Satisfacción y usabilidad",
         "Encuesta con escala de Likert a consultores y gerencia",
         "Semestral", "Gerencia / Asesor"),
    ], encabezado=["Indicador", "Lugar de medición", "Frecuencia", "Responsable"])
    doc.add_page_break()

    # ==================== PLANTILLA 8 ====================
    titulo_plantilla(doc, 8, "CHECKLIST FINAL",
                     "Verifica que todos los elementos de la implementación estén completos.")
    tabla(doc, [
        ("Producto final de la investigación (solución)", "En proceso"),
        ("Plan de trabajo y cronograma", "Completado"),
        ("Recursos identificados", "Completado"),
        ("Diagrama de proceso", "Completado"),
        ("Resultados esperados", "Completado"),
        ("Presentación y exposición de resultados", "Pendiente"),
        ("Recolección de información en curso", "En proceso"),
    ], encabezado=["Ítem", "Estado (Pendiente / En proceso / Completado)"])
    doc.add_page_break()

    # ==================== PLANTILLA 9 ====================
    titulo_plantilla(doc, 9, "EVIDENCIAS Y DOCUMENTACIÓN TÉCNICA",
                     "Documenta dónde se resguardan las evidencias y la documentación técnica de la implementación.")
    tabla(doc, [
        ("Repositorio de código fuente (GitHub)",
         "https://github.com/ravenc1/setesa_gestion_ausencias — repositorio público, rama \"main\", commit "
         "inicial 48d2836 (16/10/2026), correspondiente a la versión 1.0 del sistema SETESA Workflow."),
        ("Ubicación de evidencias",
         "Repositorio GitHub del proyecto y carpeta storage/ (subcarpetas pdf y firmas). El código se organiza "
         "en app.py (punto de entrada), src/core (autenticación, catálogos, workflow, base de datos), "
         "src/features (registro, coordinador, vigencia, dashboard) y src/services (motor PDF y firmas)."),
        ("Convención de nombres",
         "Casos de prueba: PR-0X_caso-prueba_fecha; expedientes PDF: accion_<usuario>_<id>d.pdf."),
        ("Documentación técnica",
         "docs/ESTRUCTURA.md (arquitectura y estructura de carpetas), requirements.txt (dependencias), "
         "tests/smoke_test.py (pruebas de humo), .env.example (variables de entorno), scripts/hash_passwords.py "
         "y el informe del proyecto de graduación (PG2_Proyecto_Pagina_Web_SETESA_RicardoArias.pdf)."),
        ("Responsable de custodia",
         "Ricardo Andree Sebastián Arias Conde (Investigador) / Administrador de TI de SETESA."),
        ("Restricciones de acceso",
         "Acceso restringido por RBAC; los datos sensibles solo los visualiza Gerencia. El repositorio es "
         "público y no contiene credenciales: el archivo .env está excluido mediante .gitignore."),
    ], encabezado=["Elemento", "Detalle"])

    doc.save(str(SALIDA))
    print("Documento generado:", SALIDA)


if __name__ == "__main__":
    main()
