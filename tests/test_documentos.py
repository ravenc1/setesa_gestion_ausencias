# Pruebas de integración del servicio de documentos (requieren DATABASE_URL).
#
# Verifican que el PDF oficial se genere desde la base, incluya las firmas
# capturadas, se guarde en `solicitud.ruta_pdf` y no deje temporales.

import base64
import datetime
import io
import os
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from src.core.config import FIRMAS_DIR, PDF_DIR
from src.core.database import get_connection
from src.core.solicitudes import (
    cambiar_estado,
    obtener_solicitud,
    registrar_solicitud,
)
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
)
from src.services.documentos import generar_pdf_solicitud

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requiere DATABASE_URL (pruebas de integración).",
)


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


@pytest.fixture
def ids():
    return _ids_por_rol()


def _crear_solicitud(id_usuario):
    return registrar_solicitud(
        id_usuario,
        "VACACION",
        datetime.date(2026, 10, 12),
        datetime.date(2026, 10, 16),
        "Jefe GTC",
        "Consultor",
        "C-001",
        5,
        f"PYTEST_PDF_{uuid4().hex[:10]}",
        _firma_b64(),
    )


def _limpiar(id_solicitud, ruta_pdf=None):
    if ruta_pdf and Path(ruta_pdf).exists():
        Path(ruta_pdf).unlink()
    conn = get_connection()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM solicitud WHERE id_solicitud = %s", (id_solicitud,)
                )
    finally:
        conn.close()


def test_pdf_final_con_tres_firmas_y_ruta_persistida(ids):
    id_solicitud = _crear_solicitud(ids["Consultor"])
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

        antes = set(FIRMAS_DIR.glob("temp_firma_*.png"))
        ruta = generar_pdf_solicitud(id_solicitud)
        despues = set(FIRMAS_DIR.glob("temp_firma_*.png"))

        assert Path(ruta).exists()
        assert Path(ruta).parent == PDF_DIR
        assert f"accion_{id_solicitud}_" in Path(ruta).name

        datos = obtener_solicitud(id_solicitud)
        assert datos["ruta_pdf"] == ruta

        contenido = Path(ruta).read_bytes()
        assert contenido.count(b"/Subtype /Image") == 3, (
            "El PDF final debe estampar las tres firmas"
        )
        assert despues - antes == set(), "No deben quedar imágenes temporales"
    finally:
        _limpiar(id_solicitud, ruta)


def test_pdf_sin_aprobaciones_solo_estampa_consultor(ids):
    id_solicitud = _crear_solicitud(ids["Consultor"])
    ruta = None
    try:
        ruta = generar_pdf_solicitud(id_solicitud)
        contenido = Path(ruta).read_bytes()
        assert contenido.count(b"/Subtype /Image") == 1

        # Regenerar el mismo expediente reutiliza la ruta (no acumula PDFs).
        assert generar_pdf_solicitud(id_solicitud) == ruta
    finally:
        _limpiar(id_solicitud, ruta)
