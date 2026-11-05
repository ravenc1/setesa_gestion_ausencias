# R-11: recordatorios del consultor al Coordinador GTC.
#
# Las pruebas de integración crean su propia solicitud y la eliminan al
# finalizar; los recordatorios se borran en cascada con la solicitud.

import base64
import datetime
import io
import os
from uuid import uuid4

import pytest
from PIL import Image

from src.core.database import get_connection
from src.core.recordatorios import (
    RecordatorioError,
    RecordatorioNoPermitido,
    RecordatorioReciente,
    construir_enlace_correo,
    obtener_recordatorios_pendientes,
    registrar_recordatorio,
)
from src.core.solicitudes import cambiar_estado, registrar_solicitud
from src.core.workflow import ESTADO_PENDIENTE_APROBACION_GERENCIA

requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requiere DATABASE_URL (pruebas de integración).",
)


def _firma_b64():
    img = Image.new("RGB", (120, 40), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _datos_base():
    """IDs de consultor, coordinador y administrador vigentes."""
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")

    ids = {}
    try:
        with conn.cursor() as cursor:
            for clave, rol in (
                ("consultor", "Consultor"),
                ("administrador", "Administrador"),
            ):
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
                ids[clave] = fila[0] if fila else None

            cursor.execute(
                """
                SELECT u.id_usuario, u.nombre_completo, u.correo_institucional
                FROM usuario u
                JOIN rol r ON u.id_rol = r.id_rol
                WHERE r.nombre_rol = 'Coordinador GTC'
                  AND u.estado_vigencia = TRUE
                ORDER BY u.id_usuario LIMIT 1
                """
            )
            fila = cursor.fetchone()
            if fila:
                ids["coordinador"] = fila[0]
                ids["coordinador_nombre"] = fila[1]
                ids["coordinador_correo"] = fila[2]
    finally:
        conn.close()

    faltantes = [
        clave
        for clave in ("consultor", "administrador", "coordinador")
        if not ids.get(clave)
    ]
    if faltantes:
        pytest.skip(f"Faltan usuarios vigentes: {faltantes}")
    return ids


def _eliminar(id_solicitud):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL setesa.permitir_borrado = 'on'")
            cursor.execute(
                "DELETE FROM solicitud WHERE id_solicitud = %s", (id_solicitud,)
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def solicitud():
    datos = _datos_base()
    id_solicitud = registrar_solicitud(
        datos["consultor"],
        "DUELO",
        datetime.date(2032, 1, 5),
        datetime.date(2032, 1, 6),
        datos["coordinador"],
        "Consultor",
        "C-001",
        2,
        f"PYTEST_RECORDATORIO_{uuid4().hex[:8]}",
        None,
    )
    yield id_solicitud, datos
    _eliminar(id_solicitud)


def test_enlace_correo_codifica_asunto_y_cuerpo():
    enlace = construir_enlace_correo(
        "coordinador@banco.com",
        "Recordatorio: expediente #10",
        "Línea 1\nLínea 2 & cierre",
    )
    assert enlace.startswith("mailto:coordinador@banco.com?subject=")
    assert "%20" in enlace
    assert "%26" in enlace  # ampersand codificado
    assert "%0A" in enlace  # salto de línea codificado


@requiere_bd
def test_registrar_recordatorio_queda_pendiente_para_el_banco(solicitud):
    id_solicitud, datos = solicitud

    envio = registrar_recordatorio(id_solicitud, datos["consultor"])

    assert envio["id_destinatario"] == datos["coordinador"]
    assert envio["correo"] == datos["coordinador_correo"]
    assert envio["mensaje"]

    pendientes = obtener_recordatorios_pendientes(datos["coordinador"])
    assert id_solicitud in pendientes["id_solicitud"].tolist()
    fila = pendientes[pendientes["id_solicitud"] == id_solicitud].iloc[0]
    assert fila["mensaje"] == envio["mensaje"]

    # RNF-01: el mensaje queda cifrado en reposo y se descifra al mostrarlo.
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mensaje FROM recordatorio WHERE id_solicitud = %s",
                (id_solicitud,),
            )
            crudo = cursor.fetchone()[0]
    finally:
        conn.close()
    assert crudo.startswith("fernet:")


@requiere_bd
def test_cooldown_evita_recordatorios_duplicados(solicitud):
    id_solicitud, datos = solicitud
    registrar_recordatorio(id_solicitud, datos["consultor"])

    with pytest.raises(RecordatorioReciente):
        registrar_recordatorio(id_solicitud, datos["consultor"])


@requiere_bd
def test_solo_el_dueno_del_expediente_puede_recordar(solicitud):
    id_solicitud, datos = solicitud

    with pytest.raises(RecordatorioNoPermitido):
        registrar_recordatorio(id_solicitud, datos["administrador"])


@requiere_bd
def test_no_se_permite_cuando_el_banco_ya_firmo(solicitud):
    id_solicitud, datos = solicitud
    cambiar_estado(
        id_solicitud,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        datos["coordinador"],
        "Visto bueno de prueba.",
        firma_b64=_firma_b64(),
    )

    with pytest.raises(RecordatorioNoPermitido):
        registrar_recordatorio(id_solicitud, datos["consultor"])


@requiere_bd
def test_la_firma_del_banco_marca_los_recordatorios_atendidos(solicitud):
    id_solicitud, datos = solicitud
    registrar_recordatorio(id_solicitud, datos["consultor"])

    cambiar_estado(
        id_solicitud,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        datos["coordinador"],
        "Visto bueno de prueba.",
        firma_b64=_firma_b64(),
    )

    pendientes = obtener_recordatorios_pendientes(datos["coordinador"])
    assert id_solicitud not in pendientes["id_solicitud"].tolist()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT atendido, fecha_atencion
                FROM recordatorio
                WHERE id_solicitud = %s
                """,
                (id_solicitud,),
            )
            atendido, fecha_atencion = cursor.fetchone()
    finally:
        conn.close()

    assert atendido is True
    assert fecha_atencion is not None


@requiere_bd
def test_expediente_inexistente():
    datos = _datos_base()

    with pytest.raises(RecordatorioError):
        registrar_recordatorio(2_000_000_000, datos["consultor"])
