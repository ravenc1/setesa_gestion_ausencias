# Pruebas de integración del saldo de vacaciones (RF-01 / D-03).
#
# Cada prueba crea un consultor temporal con días asignados conocidos, registra
# solicitudes y elimina todo al finalizar.

import datetime
import os
from uuid import uuid4

import pytest

from src.core.database import get_connection
from src.core.security import hash_password
from src.core.solicitudes import registrar_solicitud
from src.core.vacaciones import obtener_saldo_vacaciones
from src.core.validaciones import ValidacionError

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requiere DATABASE_URL (pruebas de integración).",
)


def _conectar():
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    return conn


@pytest.fixture
def consultor():
    """Crea un consultor temporal y lo elimina con sus solicitudes."""
    conn = _conectar()
    marca = uuid4().hex[:8]
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id_rol FROM rol WHERE nombre_rol = 'Consultor'"
            )
            fila = cursor.fetchone()
            if not fila:
                pytest.skip("No existe el rol Consultor.")
            id_rol = fila[0]

            cursor.execute(
                """
                INSERT INTO usuario
                    (id_rol, nombre_completo, correo_institucional,
                     password_hash, estado_vigencia, ultima_actividad,
                     dias_vacaciones_asignados)
                VALUES (%s, %s, %s, %s, TRUE, NOW(), %s)
                RETURNING id_usuario
                """,
                (
                    id_rol,
                    f"PYTEST Vacaciones {marca}",
                    f"pytest_vacaciones_{marca}@example.com",
                    hash_password("ClaveVacaciones123"),
                    10,
                ),
            )
            id_usuario = cursor.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    yield id_usuario

    conn = get_connection()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM solicitud WHERE id_usuario = %s", (id_usuario,)
                )
                cursor.execute(
                    "DELETE FROM usuario WHERE id_usuario = %s", (id_usuario,)
                )
    finally:
        conn.close()


def _registrar(id_usuario, tipo, inicio, fin, dias):
    return registrar_solicitud(
        id_usuario,
        tipo,
        inicio,
        fin,
        "Coordinador GTC",
        "Consultor",
        "C-001",
        dias,
        f"PYTEST_VACACIONES_{uuid4().hex[:8]}",
        None,
    )


def test_saldo_inicial(consultor):
    saldo = obtener_saldo_vacaciones(consultor, anio=2026)
    assert saldo == {
        "anio": 2026,
        "asignados": 10,
        "usados": 0,
        "disponibles": 10,
    }


def test_registro_descuenta_saldo(consultor):
    _registrar(
        consultor,
        "VACACION",
        datetime.date(2026, 3, 2),
        datetime.date(2026, 3, 3),
        2,
    )

    saldo = obtener_saldo_vacaciones(consultor, anio=2026)
    assert saldo["usados"] == 2
    assert saldo["disponibles"] == 8


def test_saldo_insuficiente_es_rechazado(consultor):
    _registrar(
        consultor,
        "VACACION",
        datetime.date(2026, 3, 2),
        datetime.date(2026, 3, 6),
        5,
    )

    with pytest.raises(ValidacionError, match="Saldo de vacaciones insuficiente"):
        _registrar(
            consultor,
            "VACACION",
            datetime.date(2026, 3, 9),
            datetime.date(2026, 3, 16),
            6,
        )

    saldo = obtener_saldo_vacaciones(consultor, anio=2026)
    assert saldo["usados"] == 5


def test_otro_anio_no_descuenta_el_actual(consultor):
    _registrar(
        consultor,
        "VACACION",
        datetime.date(2027, 1, 4),
        datetime.date(2027, 1, 5),
        2,
    )

    assert obtener_saldo_vacaciones(consultor, anio=2026)["usados"] == 0
    assert obtener_saldo_vacaciones(consultor, anio=2027)["usados"] == 2


def test_permiso_no_descuenta_vacaciones(consultor):
    _registrar(
        consultor,
        "DUELO",
        datetime.date(2026, 4, 6),
        datetime.date(2026, 4, 7),
        2,
    )

    saldo = obtener_saldo_vacaciones(consultor, anio=2026)
    assert saldo["usados"] == 0
    assert saldo["disponibles"] == 10
