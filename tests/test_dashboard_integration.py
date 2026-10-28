# Pruebas de integración del dashboard gerencial (RF-04 / HU-03).
#
# Verifican que el repositorio incluya las columnas necesarias, que los filtros
# se apliquen sobre datos reales y que el PDF final se pueda descargar con sus
# tres firmas. La solicitud de prueba se elimina al finalizar.

import base64
import datetime
import io
import os
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from src.core.database import get_connection
from src.core.reportes import filtrar_solicitudes
from src.core.solicitudes import (
    cambiar_estado,
    obtener_solicitud,
    registrar_solicitud,
)
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
)
from src.features.dashboard import obtener_solicitudes
from src.services.documentos import preparar_pdf_descarga

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requiere DATABASE_URL (pruebas de integración).",
)

COLUMNAS_ESPERADAS = {
    "id_solicitud",
    "nombre_completo",
    "tipo_ausencia",
    "fecha_inicio",
    "fecha_fin",
    "dias_solicitados",
    "estado_workflow",
    "fecha_creacion",
    "ruta_pdf",
}


def _firma_b64():
    img = Image.new("RGB", (120, 40), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _ids_por_rol():
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    ids = {}
    try:
        with conn.cursor() as cursor:
            for rol in ("Consultor", "Coordinador GTC", "Administrador"):
                cursor.execute(
                    """
                    SELECT u.id_usuario FROM usuario u
                    JOIN rol r ON u.id_rol = r.id_rol
                    WHERE r.nombre_rol = %s AND u.estado_vigencia = TRUE
                    ORDER BY u.id_usuario LIMIT 1
                    """,
                    (rol,),
                )
                fila = cursor.fetchone()
                ids[rol] = fila[0] if fila else None
    finally:
        conn.close()
    if not all(ids.values()):
        pytest.skip(f"Faltan usuarios por rol: {ids}")
    return ids


def _eliminar(id_solicitud):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM solicitud WHERE id_solicitud = %s",
                    (id_solicitud,),
                )
    finally:
        conn.close()


def test_repositorio_filtros_y_descarga_pdf_final():
    ids = _ids_por_rol()
    fecha_inicio = datetime.date(2030, 1, 7)
    fecha_fin = datetime.date(2030, 1, 11)
    id_solicitud = registrar_solicitud(
        ids["Consultor"],
        "VACACION",
        fecha_inicio,
        fecha_fin,
        "Jefe GTC",
        "Consultor",
        "C-001",
        5,
        f"PYTEST_DASHBOARD_{uuid4().hex[:10]}",
        _firma_b64(),
    )
    ruta = None
    try:
        cambiar_estado(
            id_solicitud,
            ESTADO_PENDIENTE_APROBACION_GERENCIA,
            ids["Coordinador GTC"],
            "Firma del coordinador.",
            firma_b64=_firma_b64(),
        )
        cambiar_estado(
            id_solicitud,
            ESTADO_FINALIZADA,
            ids["Administrador"],
            "Firma de gerencia.",
            firma_b64=_firma_b64(),
        )

        df = obtener_solicitudes()
        assert COLUMNAS_ESPERADAS <= set(df.columns)

        fila = df[df["id_solicitud"] == id_solicitud]
        assert len(fila) == 1
        assert fila.iloc[0]["estado_workflow"] == ESTADO_FINALIZADA

        filtrado = filtrar_solicitudes(
            df,
            nombre=fila.iloc[0]["nombre_completo"],
            estado=ESTADO_FINALIZADA,
            tipo="VACACION",
            fecha_desde=datetime.date(2030, 1, 1),
            fecha_hasta=datetime.date(2030, 1, 31),
        )
        assert id_solicitud in set(filtrado["id_solicitud"].tolist())

        ruta, contenido = preparar_pdf_descarga(id_solicitud)
        assert Path(ruta).exists()
        assert contenido.startswith(b"%PDF")
        assert contenido.count(b"/Subtype /Image") == 3

        datos = obtener_solicitud(id_solicitud)
        assert Path(datos["ruta_pdf"]) == Path(ruta)
    finally:
        if ruta is not None:
            Path(ruta).unlink(missing_ok=True)
            Path(ruta).with_suffix(".pdf.sha256").unlink(missing_ok=True)
        _eliminar(id_solicitud)
