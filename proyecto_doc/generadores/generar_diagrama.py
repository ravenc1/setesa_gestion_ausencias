# -*- coding: utf-8 -*-
"""
Generación del "Diagrama de Proceso de Implementación" (Plantilla 4) para el
proyecto de graduación: Digitalización y Automatización de Flujo de Solicitudes
de Ausencia Laboral y Gestión de Vigencia de Usuarios - SETESA.

Diseño compacto (cuadrícula 2x3 en "serpiente") para que la relación de
aspecto sea casi cuadrada y el diagrama resulte legible al insertarse en el
documento de Word.

Tecnología: Graphviz (librería `graphviz` + binario `dot`).
Salida: proyecto_doc/plantillas_llenadas/diagrama_procesos.png
"""

import os
from pathlib import Path
from graphviz import Digraph

# ---------------------------------------------------------------------------
# Configuración de rutas
# ---------------------------------------------------------------------------
GRAPHVIZ_BIN = r"C:\Users\conde\AppData\Local\Temp\opencode\graphviz\extracted\Graphviz-16.1.0-win64\bin"
os.environ["PATH"] = GRAPHVIZ_BIN + os.pathsep + os.environ.get("PATH", "")

BASE = Path(r"C:\Users\conde\OneDrive\Documentos\UMG 2026\Segundo Semestre\PG2\proyecto_setesa")
OUT_DIR = BASE / "proyecto_doc" / "plantillas_llenadas"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Las 5 fases del proceso de implementación (cronograma de 24 semanas).
# ---------------------------------------------------------------------------
FASES = [
    ("f1", "1. Planificación", "#1F6FB2", "#E8F1F9",
     "Análisis y levantamiento de<br/>requerimientos y definición del DER.<br/><B>Semanas 1 - 4</B>"),
    ("f2", "2. Desarrollo", "#C8791B", "#FBEEDD",
     "Esquema PostgreSQL y módulos<br/>RBAC, registro, FPDF y vigencia.<br/><B>Semanas 5 - 16</B>"),
    ("f3", "3. Pruebas", "#2E8B57", "#E6F4EC",
     "QA: pruebas unitarias, de caja<br/>negra, corrección de errores y UAT.<br/><B>Semanas 17 - 20</B>"),
    ("f4", "4. Despliegue", "#6B4FA0", "#EDE8F7",
     "Nube (Supabase / Render), respaldos<br/>y capacitación al personal.<br/><B>Semanas 21 - 23</B>"),
    ("f5", "5. Seguimiento", "#0E7C86", "#E2F2F3",
     "KPIs en el Dashboard, vigencia<br/>semestral y trazabilidad.<br/><B>Semana 24 en adelante</B>"),
]


def construir_diagrama() -> Digraph:
    dot = Digraph("proceso_implementacion", format="png")

    dot.attr(
        rankdir="TB",
        bgcolor="white",
        pad="0.4",
        nodesep="0.45",
        ranksep="0.55",
        splines="spline",
        fontname="Helvetica",
        labelloc="t",
        label=(
            "Diagrama de Proceso de Implementación\\n"
            "SETESA — Digitalización de Solicitudes de Ausencia\\n"
            "y Gestión de Vigencia de Usuarios"
        ),
        fontsize="15",
        fontcolor="#12395C",
    )

    dot.attr("node", shape="box", style="rounded,filled", fontname="Helvetica",
             fontsize="12", penwidth="1.6", margin="0.10,0.10")
    dot.attr("edge", color="#5B6B7B", penwidth="2.0", arrowsize="1.0")

    # Nodos de fase (etiqueta HTML con título + descripción)
    for fid, titulo, borde, relleno, descripcion in FASES:
        etiqueta = (
            f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">'
            f'<TR><TD BGCOLOR="{borde}"><FONT COLOR="white" POINT-SIZE="13"><B>{titulo}</B></FONT></TD></TR>'
            f'<TR><TD BGCOLOR="{relleno}" ALIGN="CENTER"><FONT POINT-SIZE="11">{descripcion}</FONT></TD></TR>'
            f"</TABLE>>"
        )
        dot.node(fid, label=etiqueta, color=borde)

    # Nodo de criterio de aceptación
    dot.node(
        "aceptacion",
        label=(
            '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">'
            '<TR><TD BGCOLOR="#C9A227"><FONT COLOR="white" POINT-SIZE="13"><B>Criterio de aceptación</B></FONT></TD></TR>'
            '<TR><TD BGCOLOR="#FCF6DC" ALIGN="CENTER"><FONT POINT-SIZE="11">Sistema en producción, sin pérdida'
            ' de datos<BR/>y con trazabilidad total de la &quot;Acción de Personal&quot;.</FONT></TD></TR>'
            "</TABLE>>"
        ),
        shape="box", color="#C9A227",
    )

    # ------------------------------------------------------------------
    # Distribución en cuadrícula de 2 columnas (flujo de columnas):
    #   columna izquierda :  f1 -> f2 -> f3
    #   columna derecha   :  f4 -> f5 -> aceptacion
    #   conector          :  f3 .......> f4
    # ------------------------------------------------------------------
    with dot.subgraph() as s:
        s.attr(rank="same")
        s.node("f1")
        s.node("f4")
    with dot.subgraph() as s:
        s.attr(rank="same")
        s.node("f2")
        s.node("f5")
    with dot.subgraph() as s:
        s.attr(rank="same")
        s.node("f3")
        s.node("aceptacion")

    dot.edge("f1", "f2")
    dot.edge("f2", "f3")
    dot.edge("f4", "f5")
    dot.edge("f5", "aceptacion")
    # Conector entre columnas (no altera las filas)
    dot.edge("f3", "f4", constraint="false", style="dashed", color="#C9A227")

    return dot


def main() -> None:
    dot = construir_diagrama()
    salida = OUT_DIR / "diagrama_procesos"
    # dpi alto para nitidez al insertar en Word
    dot.render(filename=str(salida), cleanup=True)
    print("Diagrama generado en:", str(salida) + ".png")


if __name__ == "__main__":
    main()
