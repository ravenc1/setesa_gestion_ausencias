# Prueba de humo de la interfaz con AppTest de Streamlit.
#
# Verifica que el login y los tres paneles por rol se rendericen sin
# excepciones. No sustituye las pruebas de integración, pero detecta errores
# de importación, de estado de sesión y de renderizado.

import os
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from src.core.database import get_connection
from src.core.security import hash_password

RUTA_APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")


def test_pantalla_login_sin_excepciones():
    at = AppTest.from_file(RUTA_APP, default_timeout=60).run()
    assert not at.exception
    assert len(at.markdown) >= 1


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)
@pytest.mark.parametrize("rol", ["Consultor", "Coordinador GTC", "Administrador"])
def test_panel_por_rol_sin_excepciones(rol):
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id_usuario, u.nombre_completo FROM usuario u
                JOIN rol r ON u.id_rol = r.id_rol
                WHERE r.nombre_rol = %s AND u.estado_vigencia = TRUE
                ORDER BY u.id_usuario LIMIT 1
                """,
                (rol,),
            )
            fila = cursor.fetchone()
    finally:
        conn.close()

    if not fila:
        pytest.skip(f"No hay usuario activo con rol {rol}.")

    at = AppTest.from_file(RUTA_APP, default_timeout=60)
    at.session_state["logged_in"] = True
    at.session_state["id_usuario"] = fila[0]
    at.session_state["nombre"] = fila[1]
    at.session_state["rol"] = rol
    at.run()

    assert not at.exception, [e.value for e in at.exception]
    assert any("Perfil de Usuario" in t.value for t in at.title)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)
def test_login_usuario_inactivo_es_rechazado():
    """QA-01: un usuario con baja lógica no puede iniciar sesión."""
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")

    correo = f"pytest_qa01_{uuid4().hex[:8]}@example.com"
    password = "ClaveQA01123"
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id_rol FROM rol WHERE nombre_rol = 'Consultor'"
            )
            id_rol = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO usuario
                    (id_rol, nombre_completo, correo_institucional,
                     password_hash, estado_vigencia, ultima_actividad)
                VALUES (%s, %s, %s, %s, FALSE, NOW())
                """,
                (id_rol, "PYTEST QA-01", correo, hash_password(password)),
            )
        conn.commit()
    finally:
        conn.close()

    try:
        at = AppTest.from_file(RUTA_APP, default_timeout=60).run()
        at.text_input[0].input(correo)
        at.text_input[1].input(password)
        at.button[0].click()
        at.run()

        assert not at.exception, [e.value for e in at.exception]
        assert any("Usuario inactivo" in e.value for e in at.error)
        # La sesión no se creó: el formulario de login sigue visible.
        assert any("Iniciar Sesión" in b.label for b in at.button)
    finally:
        conn = get_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM usuario WHERE correo_institucional = %s",
                        (correo,),
                    )
                conn.commit()
            finally:
                conn.close()
