# Funciones utilitarias puras (sin dependencia de Streamlit).

import datetime


def calcular_dias_habiles(fecha_inicio, fecha_fin):
    """Cuenta los días hábiles (lunes a viernes) entre dos fechas, inclusive."""
    dias = 0
    actual = fecha_inicio
    while actual <= fecha_fin:
        if actual.weekday() < 5:
            dias += 1
        actual += datetime.timedelta(days=1)
    return dias
