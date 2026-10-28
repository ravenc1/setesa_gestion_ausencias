# Catálogo único de estados y transiciones del workflow de solicitudes.
# Fuente: RF-03 / sección 4.9.2 y 4.12.3 del documento de proyecto
# (Ingresada, Pendiente de Firma Coordinador, Pendiente de Aprobación Gerencia,
# Finalizada).

ESTADO_INGRESADA = "Ingresada"
ESTADO_PENDIENTE_FIRMA_COORDINADOR = "Pendiente de Firma Coordinador"
ESTADO_PENDIENTE_APROBACION_GERENCIA = "Pendiente de Aprobación Gerencia"
ESTADO_FINALIZADA = "Finalizada"

ESTADOS_WORKFLOW = [
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_FINALIZADA,
]

# Grafo de transiciones permitidas. El flujo es estrictamente secuencial:
# no se puede saltar de "Ingresada" a "Finalizada" ni retroceder.
TRANSICIONES = {
    ESTADO_INGRESADA: [ESTADO_PENDIENTE_FIRMA_COORDINADOR],
    ESTADO_PENDIENTE_FIRMA_COORDINADOR: [ESTADO_PENDIENTE_APROBACION_GERENCIA],
    ESTADO_PENDIENTE_APROBACION_GERENCIA: [ESTADO_FINALIZADA],
    ESTADO_FINALIZADA: [],
}


def estado_valido(estado):
    """Indica si el estado pertenece al catálogo del workflow."""
    return estado in ESTADOS_WORKFLOW


def puede_transicionar(estado_actual, estado_nuevo):
    """Valida que el cambio de estado respete el orden del workflow."""
    return estado_nuevo in TRANSICIONES.get(estado_actual, [])


def siguiente_estado(estado_actual):
    """Devuelve el único estado siguiente permitido, o None si es final."""
    siguientes = TRANSICIONES.get(estado_actual, [])
    return siguientes[0] if siguientes else None
