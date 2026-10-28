# Pruebas unitarias del cálculo de días hábiles.

import datetime

from src.core.utils import calcular_dias_habiles


def test_lunes_a_viernes_cuenta_cinco():
    assert calcular_dias_habiles(
        datetime.date(2026, 10, 12), datetime.date(2026, 10, 16)
    ) == 5


def test_fin_de_semana_cuenta_cero():
    assert calcular_dias_habiles(
        datetime.date(2026, 10, 17), datetime.date(2026, 10, 18)
    ) == 0


def test_un_solo_dia_habil():
    assert calcular_dias_habiles(
        datetime.date(2026, 10, 12), datetime.date(2026, 10, 12)
    ) == 1


def test_rango_invertido_cuenta_cero():
    assert calcular_dias_habiles(
        datetime.date(2026, 10, 16), datetime.date(2026, 10, 12)
    ) == 0


def test_semana_completa_incluye_fin_de_semana_pero_no_lo_cuenta():
    # Lunes 12 a domingo 18: cinco días hábiles.
    assert calcular_dias_habiles(
        datetime.date(2026, 10, 12), datetime.date(2026, 10, 18)
    ) == 5
