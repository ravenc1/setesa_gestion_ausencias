# Pruebas del catálogo de feriados (RF-01 / D-04).
#
# Las de integración se omiten si no hay DATABASE_URL y limpian el feriado
# temporal que crean.

import datetime
import os

import pytest

from src.core.database import get_connection
from src.core.feriados import (
    FeriadoError,
    crear_feriado,
    eliminar_feriado,
    fechas_feriados,
    listar_feriados,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requiere DATABASE_URL (pruebas de integración).",
)

FECHA_PRUEBA = datetime.date(2099, 7, 15)


def _conectar():
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    return conn


def _limpiar_fecha(fecha):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM feriado WHERE fecha = %s", (fecha,))
    finally:
        conn.close()


@pytest.fixture
def feriado_temporal():
    _limpiar_fecha(FECHA_PRUEBA)
    yield FECHA_PRUEBA
    _limpiar_fecha(FECHA_PRUEBA)


def test_semilla_incluye_feriados_de_guatemala():
    df = listar_feriados(2026)
    fechas = set(df["fecha"].tolist())
    assert datetime.date(2026, 9, 15) in fechas
    assert datetime.date(2026, 12, 25) in fechas
    assert len(df) >= 10


def test_crear_y_eliminar_feriado(feriado_temporal):
    id_feriado = crear_feriado(feriado_temporal, "Feriado de prueba")

    assert feriado_temporal in fechas_feriados(
        feriado_temporal, feriado_temporal
    )

    assert eliminar_feriado(id_feriado) is True
    assert feriado_temporal not in fechas_feriados(
        feriado_temporal, feriado_temporal
    )
    assert eliminar_feriado(id_feriado) is False


def test_crear_mismo_dia_actualiza_nombre(feriado_temporal):
    crear_feriado(feriado_temporal, "Nombre inicial")
    crear_feriado(feriado_temporal, "Nombre actualizado")

    df = listar_feriados(2099)
    filas = df[df["fecha"] == feriado_temporal]
    assert len(filas) == 1
    assert filas.iloc[0]["nombre"] == "Nombre actualizado"


def test_nombre_vacio_es_rechazado(feriado_temporal):
    with pytest.raises(FeriadoError):
        crear_feriado(feriado_temporal, "   ")


def test_rango_invertido_devuelve_conjunto_vacio():
    assert fechas_feriados(
        datetime.date(2026, 12, 31), datetime.date(2026, 1, 1)
    ) == set()
