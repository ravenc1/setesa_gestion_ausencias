# Fase 20: expiración de la sesión (tesis 4.2: "sesiones seguras", OWASP).
#
# Dos plazos, ambos configurables por variable de entorno:
#   SESSION_IDLE_MINUTES  inactividad máxima entre dos acciones (30 por defecto)
#   SESSION_MAX_HOURS     duración máxima de una sesión (8 por defecto)
#
# La sesión vive en st.session_state (servidor). La comprobación se hace en
# cada ejecución de la página, así que cualquier clic después del plazo cierra
# la sesión; una pestaña abandonada no puede reutilizarse horas después.

import datetime

from src.core.config import obtener_variable

IDLE_MINUTOS_DEFAULT = 30
MAX_HORAS_DEFAULT = 8

CLAVE_INICIO = "sesion_inicio"
CLAVE_ULTIMA = "sesion_ultima_interaccion"

MOTIVO_INACTIVIDAD = "inactividad"
MOTIVO_DURACION = "duracion"


def _numero(nombre, por_defecto):
    try:
        valor = float(obtener_variable(nombre) or por_defecto)
    except (TypeError, ValueError):
        return por_defecto
    return valor if valor > 0 else por_defecto


def limite_inactividad():
    return datetime.timedelta(minutes=_numero("SESSION_IDLE_MINUTES", IDLE_MINUTOS_DEFAULT))


def limite_duracion():
    return datetime.timedelta(hours=_numero("SESSION_MAX_HOURS", MAX_HORAS_DEFAULT))


def iniciar(estado, ahora=None):
    """Marca el inicio de la sesión en el estado de Streamlit."""
    ahora = ahora or datetime.datetime.now()
    estado[CLAVE_INICIO] = ahora
    estado[CLAVE_ULTIMA] = ahora


def motivo_expiracion(estado, ahora=None, idle=None, maximo=None):
    """Devuelve el motivo por el que la sesión expiró, o None si sigue vigente.

    Una sesión iniciada antes de la Fase 20 (sin marcas) se considera nueva.
    """
    ahora = ahora or datetime.datetime.now()
    idle = idle or limite_inactividad()
    maximo = maximo or limite_duracion()

    inicio = estado.get(CLAVE_INICIO)
    ultima = estado.get(CLAVE_ULTIMA)
    if inicio is None or ultima is None:
        iniciar(estado, ahora)
        return None
    if ahora - inicio > maximo:
        return MOTIVO_DURACION
    if ahora - ultima > idle:
        return MOTIVO_INACTIVIDAD
    return None


def registrar_interaccion(estado, ahora=None):
    estado[CLAVE_ULTIMA] = ahora or datetime.datetime.now()


def mensaje_expiracion(motivo):
    if motivo == MOTIVO_DURACION:
        horas = limite_duracion().total_seconds() / 3600
        return (
            f"Su sesión superó la duración máxima de {horas:g} hora(s). "
            "Inicie sesión nuevamente."
        )
    minutos = limite_inactividad().total_seconds() / 60
    return (
        f"Su sesión se cerró por inactividad ({minutos:g} minutos). "
        "Inicie sesión nuevamente."
    )
