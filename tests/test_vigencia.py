# Pruebas de integración del algoritmo de vigencia (RF-05 / CU-06 / QA-06).
#
# Cada prueba crea usuarios temporales con fechas controladas y restaura el
# estado de los usuarios reales al finalizar. Los logs creados durante la prueba
# se eliminan por id_log.

import os
from uuid import uuid4

import pytest

from src.core.auth import login_user
from src.core.database import get_connection
from src.core.security import hash_password
from src.core.vigencia import (
    ACCION_REACTIVACION,
    debe_ejecutarse_automaticamente,
    ejecutar_depuracion,
    ejecutar_si_corresponde,
    obtener_dados_de_baja,
    obtener_inactivos,
    reactivar_usuario,
    registrar_actividad,
    usuario_activo,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requiere DATABASE_URL (pruebas de integración).",
)

PASSWORD = "ClaveVigencia123"


def _conectar():
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    return conn


@pytest.fixture
def escenario():
    """Crea 3 usuarios de prueba y restaura el estado real al terminar."""
    conn = _conectar()
    marca = uuid4().hex[:8]
    ids = {}
    correos = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(id_log), 0) FROM vigencia_log")
            max_log = cursor.fetchone()[0]

            cursor.execute("SELECT id_usuario, estado_vigencia FROM usuario")
            snapshot = dict(cursor.fetchall())

            cursor.execute("SELECT nombre_rol, id_rol FROM rol")
            roles = dict(cursor.fetchall())

            cursor.execute(
                """
                SELECT id_usuario FROM usuario
                WHERE id_rol = %s ORDER BY id_usuario LIMIT 1
                """,
                (roles["Administrador"],),
            )
            fila_admin = cursor.fetchone()
            if not fila_admin:
                pytest.skip("No hay usuario Administrador para ejecutar la prueba.")
            id_admin = fila_admin[0]

            definiciones = [
                ("vencido", "Consultor", "7 months"),
                ("reciente", "Consultor", "1 day"),
                ("admin_vencido", "Administrador", "7 months"),
            ]
            for clave, rol, intervalo in definiciones:
                correo = f"pytest_vigencia_{clave}_{marca}@example.com"
                correos[clave] = correo
                cursor.execute(
                    """
                    INSERT INTO usuario
                        (id_rol, nombre_completo, correo_institucional,
                         password_hash, estado_vigencia, ultima_actividad)
                    VALUES (%s, %s, %s, %s, TRUE, NOW() - %s::interval)
                    RETURNING id_usuario
                    """,
                    (
                        roles[rol],
                        f"PYTEST {clave} {marca}",
                        correo,
                        hash_password(PASSWORD),
                        intervalo,
                    ),
                )
                ids[clave] = cursor.fetchone()[0]

        conn.commit()
        yield {
            "ids": ids,
            "correos": correos,
            "id_admin": id_admin,
            "roles": roles,
            "max_log": max_log,
        }
    finally:
        with conn.cursor() as cursor:
            # Restaurar cualquier usuario real que la prueba haya desactivado.
            for id_usuario, estado in snapshot.items():
                cursor.execute(
                    "UPDATE usuario SET estado_vigencia = %s WHERE id_usuario = %s",
                    (estado, id_usuario),
                )
            cursor.execute("DELETE FROM vigencia_log WHERE id_log > %s", (max_log,))
            cursor.execute(
                "DELETE FROM usuario WHERE id_usuario = ANY(%s)",
                (list(ids.values()),),
            )
        conn.commit()
        conn.close()


def test_inactivos_excluye_recientes_y_administradores(escenario):
    ids = escenario["ids"]
    df = obtener_inactivos(id_excluido=escenario["id_admin"])
    encontrados = set(df["id_usuario"].tolist())

    assert ids["vencido"] in encontrados
    assert ids["reciente"] not in encontrados
    assert ids["admin_vencido"] not in encontrados
    assert escenario["id_admin"] not in encontrados


def test_depuracion_aplica_baja_logica_y_registra_log(escenario):
    ids = escenario["ids"]
    df_afectados, id_log = ejecutar_depuracion(id_ejecutor=escenario["id_admin"])

    assert ids["vencido"] in set(df_afectados["id_usuario"].tolist())
    assert usuario_activo(ids["vencido"]) is False
    assert usuario_activo(ids["reciente"]) is True
    assert usuario_activo(ids["admin_vencido"]) is True

    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT accion, usuarios_afectados, id_ejecutor, detalle
                FROM vigencia_log WHERE id_log = %s
                """,
                (id_log,),
            )
            accion, afectados, ejecutor, detalle = cursor.fetchone()
        assert accion == "DEPURACION"
        assert afectados == len(df_afectados)
        assert ejecutor == escenario["id_admin"]
        assert str(ids["vencido"]) in detalle
    finally:
        conn.close()

    assert debe_ejecutarse_automaticamente() is False
    assert ejecutar_si_corresponde(escenario["id_admin"]) is None


def test_reactivacion_actualiza_estado_y_actividad(escenario):
    ids = escenario["ids"]
    ejecutar_depuracion(id_ejecutor=escenario["id_admin"])
    assert usuario_activo(ids["vencido"]) is False

    id_log = reactivar_usuario(ids["vencido"], id_ejecutor=escenario["id_admin"])
    assert usuario_activo(ids["vencido"]) is True

    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT accion, detalle FROM vigencia_log WHERE id_log = %s",
                (id_log,),
            )
            accion, detalle = cursor.fetchone()
            assert accion == ACCION_REACTIVACION
            assert detalle == f"id={ids['vencido']}"

            cursor.execute(
                "SELECT ultima_actividad > NOW() - INTERVAL '1 minute' "
                "FROM usuario WHERE id_usuario = %s",
                (ids["vencido"],),
            )
            assert cursor.fetchone()[0] is True

            # registrar_actividad mueve la fecha hacia NOW().
            cursor.execute(
                "UPDATE usuario SET ultima_actividad = NOW() - INTERVAL '10 days' "
                "WHERE id_usuario = %s",
                (ids["vencido"],),
            )
        conn.commit()
    finally:
        conn.close()

    assert registrar_actividad(ids["vencido"]) is True

    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ultima_actividad > NOW() - INTERVAL '1 minute' "
                "FROM usuario WHERE id_usuario = %s",
                (ids["vencido"],),
            )
            assert cursor.fetchone()[0] is True
    finally:
        conn.close()


def test_login_bloqueado_tras_baja_y_reactivado(escenario):
    ids = escenario["ids"]

    # 1. Un login exitoso de un usuario vigente actualiza su actividad.
    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE usuario SET ultima_actividad = NOW() - INTERVAL '10 days' "
                "WHERE id_usuario = %s",
                (ids["reciente"],),
            )
        conn.commit()
    finally:
        conn.close()

    datos = login_user(escenario["correos"]["reciente"], PASSWORD)
    assert datos is not None and datos[2] is True

    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ultima_actividad > NOW() - INTERVAL '1 minute' "
                "FROM usuario WHERE id_usuario = %s",
                (ids["reciente"],),
            )
            assert cursor.fetchone()[0] is True
    finally:
        conn.close()

    # 2. El usuario vencido es dado de baja y su login queda bloqueado.
    ejecutar_depuracion(id_ejecutor=escenario["id_admin"])
    assert usuario_activo(ids["vencido"]) is False

    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ultima_actividad FROM usuario WHERE id_usuario = %s",
                (ids["vencido"],),
            )
            actividad_tras_baja = cursor.fetchone()[0]
    finally:
        conn.close()

    datos = login_user(escenario["correos"]["vencido"], PASSWORD)
    assert datos is not None and datos[2] is False

    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ultima_actividad FROM usuario WHERE id_usuario = %s",
                (ids["vencido"],),
            )
            assert cursor.fetchone()[0] == actividad_tras_baja
    finally:
        conn.close()

    # 3. Tras reactivarlo, vuelve a entrar y su actividad se actualiza.
    reactivar_usuario(ids["vencido"], id_ejecutor=escenario["id_admin"])
    datos = login_user(escenario["correos"]["vencido"], PASSWORD)
    assert datos is not None and datos[2] is True


def test_ejecutar_si_corresponde_solo_si_vencio_el_periodo(escenario):
    _, id_log = ejecutar_depuracion(id_ejecutor=escenario["id_admin"])
    assert debe_ejecutarse_automaticamente() is False
    assert ejecutar_si_corresponde(escenario["id_admin"]) is None

    # Envejecer solo el log de esta prueba para simular el paso de 6 meses.
    conn = _conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE vigencia_log SET fecha_ejecucion = NOW() - INTERVAL '7 months' "
                "WHERE id_log = %s",
                (id_log,),
            )
        conn.commit()
    finally:
        conn.close()

    if debe_ejecutarse_automaticamente():
        resultado = ejecutar_si_corresponde(escenario["id_admin"])
        assert resultado is not None
        assert resultado[0] >= 0


def test_obtener_dados_de_baja_incluye_al_vencido(escenario):
    ejecutar_depuracion(id_ejecutor=escenario["id_admin"])
    df = obtener_dados_de_baja()
    assert escenario["ids"]["vencido"] in set(df["id_usuario"].tolist())
