# Servicio de documentos oficiales.
#
# Genera el PDF de una solicitud a partir de los datos persistidos en la base
# (incluidas las firmas ya capturadas) y guarda la ruta resultante en
# `solicitud.ruta_pdf`. Así cualquier panel obtiene el mismo documento sin
# duplicar la lógica de armado.

from src.core.solicitudes import actualizar_ruta_pdf, obtener_solicitud
from src.services.motor_pdf import generar_pdf_accion_personal


def generar_pdf_solicitud(id_solicitud):
    """Genera y persiste el PDF oficial del expediente.

    Devuelve la ruta del archivo. Lanza ValueError si la solicitud no existe.
    """
    datos = obtener_solicitud(id_solicitud)
    if not datos:
        raise ValueError(f"No existe la solicitud con id {id_solicitud}.")

    ruta = generar_pdf_accion_personal(
        datos["nombre_completo"],
        datos["jefe_gtc"] or "",
        datos["puesto"] or "",
        datos["codigo_empleado"] or "",
        datos["tipo_ausencia"],
        datos["fecha_inicio"],
        datos["fecha_fin"],
        datos["dias_solicitados"] or 0,
        datos["explicacion"] or "",
        datos["estado_workflow"],
        fecha_creacion=datos["fecha_creacion"],
        firma_empleado_b64=datos["firma_empleado"],
        firma_jefe_b64=datos["firma_jefe_gtc"],
        firma_gerencia_b64=datos["firma_gerencia"],
        id_solicitud=id_solicitud,
    )
    actualizar_ruta_pdf(id_solicitud, ruta)
    return ruta
