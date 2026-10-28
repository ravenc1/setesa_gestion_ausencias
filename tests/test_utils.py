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


def test_feriado_no_cuenta_como_habil():
    # Jueves 24 a lunes 28; el viernes 25 es feriado.
    assert calcular_dias_habiles(
        datetime.date(2026, 12, 24),
        datetime.date(2026, 12, 28),
        feriados={datetime.date(2026, 12, 25)},
    ) == 2


def test_feriado_en_fin_de_semana_no_altera_el_conteo():
    # Sábado 31 de octubre y domingo 1 de noviembre (feriado): 0 hábiles.
    assert calcular_dias_habiles(
        datetime.date(2026, 10, 31),
        datetime.date(2026, 11, 1),
        feriados={datetime.date(2026, 11, 1)},
    ) == 0


def test_feriados_acepta_datetime():
    assert calcular_dias_habiles(
        datetime.datetime(2026, 12, 24, 8, 0),
        datetime.datetime(2026, 12, 28, 18, 0),
        feriados={datetime.datetime(2026, 12, 25, 0, 0)},
    ) == 2
