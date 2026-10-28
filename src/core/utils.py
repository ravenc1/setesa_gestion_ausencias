# Funciones utilitarias puras (sin dependencia de Streamlit).

import datetime


def _a_fecha(valor):
    if isinstance(valor, datetime.datetime):
        return valor.date()
    return valor


def calcular_dias_habiles(fecha_inicio, fecha_fin, feriados=None):
    """Cuenta los días hábiles (lunes a viernes) entre dos fechas, inclusive.

    `feriados` es una colección opcional de fechas que se excluyen del conteo
    (RF-01 / decisión D-04).
    """
    fecha_inicio = _a_fecha(fecha_inicio)
    fecha_fin = _a_fecha(fecha_fin)
    feriados = {_a_fecha(fecha) for fecha in (feriados or [])}

    dias = 0
    actual = fecha_inicio
    while actual <= fecha_fin:
        if actual.weekday() < 5 and actual not in feriados:
            dias += 1
        actual += datetime.timedelta(days=1)
    return dias
