# Fase 14: módulo "Mis datos" (actualización de datos cada 6 meses).

import datetime

import pytest

from src.core import perfil
from src.core.perfil import PerfilError


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("5555-1234", "55551234"),
        ("5555 1234", "55551234"),
        ("+502 5555-1234", "+50255551234"),
        ("(502) 5555 1234", "50255551234"),
    ],
)
def test_normaliza_telefonos_validos(entrada, esperado):
    assert perfil.normalizar_telefono(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "1234", "5555-12a4", "+"])
def test_rechaza_telefonos_invalidos(entrada):
    with pytest.raises(PerfilError):
        perfil.normalizar_telefono(entrada)


def test_consultor_actualiza_puesto_codigo_y_telefono():
    datos = perfil.validar_datos("Consultor", " Analista ", " C-010 ", "5555-1234")
    assert datos == {
        "puesto": "Analista",
        "codigo_empleado": "C-010",
        "telefono": "55551234",
    }


def test_consultor_exige_codigo_de_empleado():
    with pytest.raises(PerfilError, match="código"):
        perfil.validar_datos("Consultor", "Analista", "", "55551234")


def test_contabilidad_solo_actualiza_puesto_y_telefono():
    datos = perfil.validar_datos("Contabilidad", "Contadora", "C-999", "55551234")
    assert datos == {"puesto": "Contadora", "telefono": "55551234"}


@pytest.mark.parametrize("rol", ["Coordinador GTC", "Administrador", "IT"])
def test_roles_excluidos_no_actualizan(rol):
    assert not perfil.requiere_actualizacion(rol)
    with pytest.raises(PerfilError):
        perfil.validar_datos(rol, "Puesto", "C-1", "55551234")


def test_fecha_limite_es_seis_meses_despues():
    assert perfil.fecha_limite(datetime.datetime(2026, 5, 10, 8, 30)) == (
        datetime.date(2026, 11, 10)
    )
    # Fin de mes: 31 de agosto + 6 meses = 28 de febrero.
    assert perfil.fecha_limite(datetime.date(2026, 8, 31)) == datetime.date(2027, 2, 28)


def test_aviso_empieza_30_dias_antes():
    actualizado = datetime.date(2026, 5, 10)  # vence el 10/11/2026
    assert perfil.dias_restantes(actualizado, hoy=datetime.date(2026, 10, 11)) == 30
    assert perfil.en_periodo_de_aviso(actualizado, hoy=datetime.date(2026, 10, 11))
    assert not perfil.en_periodo_de_aviso(actualizado, hoy=datetime.date(2026, 10, 10))
    assert perfil.en_periodo_de_aviso(actualizado, hoy=datetime.date(2026, 11, 12))
