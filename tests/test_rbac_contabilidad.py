# RBAC del rol Contabilidad (HU-03 / D-02).
#
# Contabilidad comparte el repositorio de expedientes con Gerencia, pero en modo
# consulta: no autoriza, no firma y no administra vigencia ni feriados.

import datetime
import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from src.core.database import get_connection
from src.core.security import hash_password
from src.core.solicitudes import registrar_solicitud

RUTA_APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")

requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)


def _crear_usuario_contabilidad():
    """Crea un usuario temporal con rol Contabilidad y devuelve sus datos."""
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")

    correo = f"pytest_conta_{uuid4().hex[:8]}@example.com"
    password = "ClaveConta123"
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rol (nombre_rol, descripcion_rol)
                VALUES ('Contabilidad', 'Solo lectura: consulta y descarga.')
                ON CONFLICT (nombre_rol) DO NOTHING
                """
            )
            cursor.execute(
                "SELECT id_rol FROM rol WHERE nombre_rol = 'Contabilidad'"
            )
            id_rol = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO usuario
                    (id_rol, nombre_completo, correo_institucional,
                     password_hash, estado_vigencia, ultima_actividad)
                VALUES (%s, %s, %s, %s, TRUE, NOW())
                RETURNING id_usuario
                """,
                (
                    id_rol,
                    "PYTEST CONTABILIDAD",
                    correo,
                    hash_password(password),
                ),
            )
            id_usuario = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return id_usuario, correo


def _eliminar_usuario(correo):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM usuario WHERE correo_institucional = %s", (correo,)
            )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _solicitud_de_prueba():
    """Crea una solicitud temporal para que el panel tenga expedientes.

    El panel no muestra el repositorio ni las acciones si la base está vacía.
    """
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    marca = uuid4().hex[:8]
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.id_usuario FROM usuario u
                    JOIN rol r ON u.id_rol = r.id_rol
                    WHERE r.nombre_rol = 'Consultor' AND u.estado_vigencia = TRUE
                    ORDER BY u.id_usuario LIMIT 1
                    """
                )
                consultor = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT u.id_usuario FROM usuario u
                    JOIN rol r ON u.id_rol = r.id_rol
                    WHERE r.nombre_rol = 'Coordinador GTC' AND u.estado_vigencia = TRUE
                    ORDER BY u.id_usuario LIMIT 1
                    """
                )
                coordinador = cursor.fetchone()
    finally:
        conn.close()
    if not consultor or not coordinador:
        pytest.skip("Faltan un Consultor y un Coordinador GTC vigentes.")

    id_solicitud = registrar_solicitud(
        consultor[0], "DUELO", datetime.date(2035, 3, 5),
        datetime.date(2035, 3, 6), coordinador[0], "Consultor", "C-001", 2,
        f"PYTEST_RBAC_{marca}", None,
    )
    try:
        yield id_solicitud
    finally:
        conn = get_connection()
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET LOCAL setesa.permitir_borrado = 'on'")
                    cursor.execute(
                        "DELETE FROM solicitud WHERE id_solicitud = %s",
                        (id_solicitud,),
                    )
        finally:
            conn.close()


def _sesion(rol, id_usuario=None, nombre="PYTEST"):
    at = AppTest.from_file(RUTA_APP, default_timeout=60)
    at.session_state["logged_in"] = True
    at.session_state["id_usuario"] = id_usuario
    at.session_state["nombre"] = nombre
    at.session_state["rol"] = rol
    return at.run()


@requiere_bd
def test_panel_contabilidad_sin_excepciones_y_en_solo_lectura():
    id_usuario, correo = _crear_usuario_contabilidad()
    try:
        with _solicitud_de_prueba():
            at = _sesion("Contabilidad", id_usuario, "PYTEST CONTABILIDAD")

        assert not at.exception, [e.value for e in at.exception]
        assert any(
            "Contabilidad y RR.HH." in m.value for m in at.markdown
        ), "No se renderizó el panel de Contabilidad."
        assert any(
            "Descarga del expediente final" in m.value for m in at.markdown
        ), "Contabilidad debe poder descargar el PDF final (HU-03)."

        # Sin acciones de autorización.
        etiquetas = [b.label for b in at.button]
        assert not any("Aprobar, Firmar y Finalizar" in e for e in etiquetas)
        assert not any(
            "Gestión de Workflow" in m.value for m in at.markdown
        ), "Contabilidad no debe ver la gestión de workflow."
    finally:
        _eliminar_usuario(correo)


@requiere_bd
def test_contabilidad_no_accede_a_vigencia_ni_feriados():
    id_usuario, correo = _crear_usuario_contabilidad()
    try:
        at = _sesion("Contabilidad", id_usuario, "PYTEST CONTABILIDAD")

        assert not at.exception, [e.value for e in at.exception]
        # El panel gerencial usa tres pestañas; Contabilidad no debe tener ninguna.
        assert len(at.tabs) == 0
        etiquetas = " ".join(t.label for t in at.tabs)
        assert "Vigencia" not in etiquetas
        assert "Feriados" not in etiquetas
    finally:
        _eliminar_usuario(correo)


@requiere_bd
def test_gerencia_conserva_pestanas_y_autorizacion():
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id_usuario, u.nombre_completo FROM usuario u
                JOIN rol r ON u.id_rol = r.id_rol
                WHERE r.nombre_rol = 'Administrador'
                  AND u.estado_vigencia = TRUE
                ORDER BY u.id_usuario LIMIT 1
                """
            )
            fila = cursor.fetchone()
    finally:
        conn.close()

    if not fila:
        pytest.skip("No hay usuario activo con rol Administrador.")

    with _solicitud_de_prueba():
        at = _sesion("Administrador", fila[0], fila[1])
    assert not at.exception, [e.value for e in at.exception]
    assert any("Panel de Control Gerencial" in m.value for m in at.markdown)
    # Dashboard, Reasignar Coordinador (Fase 12), Vigencia y Feriados.
    assert len(at.tabs) == 4
    assert any("Gestión de Workflow" in m.value for m in at.markdown)
