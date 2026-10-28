# Pruebas unitarias de las validaciones de negocio (H-16 / RF-01).

import datetime

import pytest

from src.core.validaciones import (
    ValidacionError,
    validar_fechas,
    validar_solicitud,
)


def test_fechas_validas():
    assert validar_fechas(
        datetime.date(2026, 10, 12), datetime.date(2026, 10, 16)
    ) is True


def test_mismo_dia_es_valido():
    assert validar_fechas(
        datetime.date(2026, 10, 12), datetime.date(2026, 10, 12)
    ) is True


def test_rango_invertido_es_rechazado():
    with pytest.raises(ValidacionError, match="no puede ser anterior"):
        validar_fechas(
            datetime.date(2026, 10, 16), datetime.date(2026, 10, 12)
        )


def test_fechas_nulas_son_rechazadas():
    with pytest.raises(ValidacionError, match="obligatorias"):
        validar_fechas(None, datetime.date(2026, 10, 12))


def test_rango_sin_dias_habiles_es_rechazado():
    with pytest.raises(ValidacionError, match="días hábiles"):
        validar_solicitud(
            1,
            "DUELO",
            datetime.date(2026, 10, 17),
            datetime.date(2026, 10, 18),
            0,
        )


def test_permiso_valido_no_consulta_saldo():
    # Para tipos distintos de VACACION no se consulta la base.
    assert validar_solicitud(
        1,
        "DUELO",
        datetime.date(2026, 10, 12),
        datetime.date(2026, 10, 13),
        2,
    ) is None
