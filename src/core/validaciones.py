# Validaciones de negocio del registro de solicitudes (H-16 / RF-01).
#
# Se ejecutan en el servidor, no solo en el formulario, para que ninguna
# solicitud pueda saltarse las reglas aunque se llame al servicio directamente.

from src.core.vacaciones import TIPO_VACACION, obtener_saldo_vacaciones


class ValidacionError(ValueError):
    """La solicitud no cumple una regla de negocio."""


def validar_fechas(fecha_inicio, fecha_fin):
    """Exige fechas presentes y un rango no invertido."""
    if fecha_inicio is None or fecha_fin is None:
        raise ValidacionError("Las fechas de inicio y fin son obligatorias.")
    if fecha_fin < fecha_inicio:
        raise ValidacionError(
            "La fecha de fin no puede ser anterior a la fecha de inicio."
        )
    return True


def validar_saldo_vacaciones(
    id_usuario, tipo_ausencia, dias_solicitados, fecha_inicio=None, anio=None
):
    """Impide solicitar más días de vacaciones de los disponibles."""
    if tipo_ausencia != TIPO_VACACION:
        return None

    saldo = obtener_saldo_vacaciones(
        id_usuario, anio=anio, fecha_referencia=fecha_inicio
    )
    if dias_solicitados > saldo["disponibles"]:
        raise ValidacionError(
            "Saldo de vacaciones insuficiente: solicita "
            f"{dias_solicitados} día(s) y solo tiene "
            f"{saldo['disponibles']} disponible(s) en {saldo['anio']}."
        )
    return saldo


def validar_solicitud(
    id_usuario,
    tipo_ausencia,
    fecha_inicio,
    fecha_fin,
    dias_solicitados,
    anio=None,
):
    """Aplica todas las reglas previas al registro."""
    validar_fechas(fecha_inicio, fecha_fin)
    if dias_solicitados is None or dias_solicitados <= 0:
        raise ValidacionError(
            "El rango seleccionado no contiene días hábiles."
        )
    return validar_saldo_vacaciones(
        id_usuario,
        tipo_ausencia,
        dias_solicitados,
        fecha_inicio=fecha_inicio,
        anio=anio,
    )
