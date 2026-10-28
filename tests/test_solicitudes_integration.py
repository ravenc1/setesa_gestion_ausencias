# Pruebas de integración contra PostgreSQL (se omiten si no hay DATABASE_URL).
#
# Cada prueba crea su propia solicitud y la elimina al finalizar. El historial
# se borra en cascada (ON DELETE CASCADE).

import base64
import datetime
import io
import os
from uuid import uuid4

import pytest
from PIL import Image

from src.core.database import get_connection
from src.core.solicitudes import (
    FirmaRequerida,
    SolicitudNoEncontrada,
    TransicionInvalida,
    cambiar_estado,
    obtener_estado,
    obtener_historial,
    obtener_solicitud,
    registrar_solicitud,
)
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)

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


def _eliminar(id_solicitud):
    conn = get_connection()
    if not conn:
        return 0
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM solicitud WHERE id_solicitud = %s", (id_solicitud,)
                )
                cursor.execute(
                    "SELECT COUNT(*) FROM solicitud_historial WHERE id_solicitud = %s",
                    (id_solicitud,),
                )
                return cursor.fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def ids():
    return _ids_por_rol()


@pytest.fixture
def solicitud(ids):
    marca = f"PYTEST_{uuid4().hex[:10]}"
    id_solicitud = registrar_solicitud(
        ids["Consultor"],
        "VACACION",
        datetime.date(2026, 10, 12),
        datetime.date(2026, 10, 16),
        "Jefe GTC",
        "Consultor",
        "C-001",
        5,
        marca,
        None,
    )
    yield id_solicitud, marca
    restantes = _eliminar(id_solicitud)
    assert restantes == 0, "El historial no se eliminó en cascada"


def test_registro_deja_estado_pendiente_y_historial(solicitud):
    id_solicitud, _ = solicitud

    assert obtener_estado(id_solicitud) == ESTADO_PENDIENTE_FIRMA_COORDINADOR

    historial = obtener_historial(id_solicitud)
    assert len(historial) == 2
    assert list(historial["estado_nuevo"]) == [
        ESTADO_INGRESADA,
        ESTADO_PENDIENTE_FIRMA_COORDINADOR,
    ]
    assert historial["estado_anterior"].isna().iloc[0]
    assert historial["actor"].notna().all()


def test_transicion_invalida_no_modifica_el_estado(solicitud, ids):
    id_solicitud, _ = solicitud

    with pytest.raises(TransicionInvalida):
        cambiar_estado(id_solicitud, ESTADO_FINALIZADA, ids["Administrador"])

    assert obtener_estado(id_solicitud) == ESTADO_PENDIENTE_FIRMA_COORDINADOR


def test_flujo_completo_con_historial(solicitud, ids):
    id_solicitud, _ = solicitud

    cambiar_estado(
        id_solicitud,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        ids["Coordinador GTC"],
        "Visto bueno de prueba.",
        firma_b64=_firma_b64(),
    )
    cambiar_estado(
        id_solicitud,
        ESTADO_FINALIZADA,
        ids["Administrador"],
        "Cierre de prueba.",
        firma_b64=_firma_b64(),
    )

    assert obtener_estado(id_solicitud) == ESTADO_FINALIZADA
    historial = obtener_historial(id_solicitud)
    assert len(historial) == 4
    assert list(historial["estado_nuevo"]) == [
        ESTADO_INGRESADA,
        ESTADO_PENDIENTE_FIRMA_COORDINADOR,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        ESTADO_FINALIZADA,
    ]


def test_firma_es_obligatoria_en_transiciones_de_firma(solicitud, ids):
    id_solicitud, _ = solicitud

    with pytest.raises(FirmaRequerida):
        cambiar_estado(
            id_solicitud,
            ESTADO_PENDIENTE_APROBACION_GERENCIA,
            ids["Coordinador GTC"],
        )

    assert obtener_estado(id_solicitud) == ESTADO_PENDIENTE_FIRMA_COORDINADOR


def test_firmas_se_persisten_en_la_solicitud(solicitud, ids):
    id_solicitud, _ = solicitud
    firma_coordinador = _firma_b64()
    firma_gerencia = _firma_b64()

    cambiar_estado(
        id_solicitud,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        ids["Coordinador GTC"],
        "Firma del coordinador.",
        firma_b64=firma_coordinador,
    )
    datos = obtener_solicitud(id_solicitud)
    assert datos["firma_jefe_gtc"] == firma_coordinador
    assert datos["firma_gerencia"] is None

    cambiar_estado(
        id_solicitud,
        ESTADO_FINALIZADA,
        ids["Administrador"],
        "Firma de gerencia.",
        firma_b64=firma_gerencia,
    )
    datos = obtener_solicitud(id_solicitud)
    assert datos["firma_jefe_gtc"] == firma_coordinador
    assert datos["firma_gerencia"] == firma_gerencia


def test_solicitud_inexistente(ids):
    with pytest.raises(SolicitudNoEncontrada):
        cambiar_estado(2_000_000_000, ESTADO_FINALIZADA, ids["Administrador"])


def test_historial_se_elimina_en_cascada(ids):
    id_solicitud = registrar_solicitud(
        ids["Consultor"],
        "DUELO",
        datetime.date(2026, 11, 2),
        datetime.date(2026, 11, 3),
        "Jefe GTC",
        "Consultor",
        "C-002",
        2,
        f"PYTEST_CASCADA_{uuid4().hex[:8]}",
        None,
    )
    assert len(obtener_historial(id_solicitud)) == 2
    assert _eliminar(id_solicitud) == 0
