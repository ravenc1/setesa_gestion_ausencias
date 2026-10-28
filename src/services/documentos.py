# Servicio de documentos oficiales.
#
# Genera el PDF de una solicitud a partir de los datos persistidos en la base
# (incluidas las firmas ya capturadas), guarda la ruta resultante en
# `solicitud.ruta_pdf` y registra su sello SHA-256 en `solicitud.pdf_hash`
# (H-13). Así cualquier panel obtiene el mismo documento sin duplicar la lógica
# de armado y puede verificar que no fue alterado.

import hashlib
from pathlib import Path

from src.core.logging_config import obtener_logger
from src.core.solicitudes import (
    actualizar_hash_pdf,
    actualizar_ruta_pdf,
    obtener_solicitud,
)
from src.services.motor_pdf import generar_pdf_accion_personal

logger = obtener_logger("setesa.documentos")

BLOQUE_LECTURA = 64 * 1024


def calcular_sha256(ruta):
    """Calcula el SHA-256 de un archivo por bloques."""
    digest = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(BLOQUE_LECTURA), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _ruta_sello(ruta):
    return Path(ruta).with_suffix(".pdf.sha256")


def _escribir_sello(ruta, sello):
    """Deja un archivo .sha256 junto al PDF (formato compatible con sha256sum)."""
    _ruta_sello(ruta).write_text(
        f"{sello}  {Path(ruta).name}\n", encoding="utf-8"
    )


def generar_pdf_solicitud(id_solicitud):
    """Genera, sella y persiste el PDF oficial del expediente.

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

    sello = calcular_sha256(ruta)
    actualizar_ruta_pdf(id_solicitud, ruta)
    actualizar_hash_pdf(id_solicitud, sello)
    _escribir_sello(ruta, sello)
    logger.info("PDF de la solicitud %s generado (sha256=%s)", id_solicitud, sello)
    return ruta


def preparar_pdf_descarga(id_solicitud, regenerar=False):
    """Devuelve (ruta, contenido) del PDF oficial listo para descargar.

    Reutiliza `solicitud.ruta_pdf` si el archivo existe; si falta, lo genera
    desde la base. Con `regenerar=True` siempre reconstruye el documento.
    """
    datos = obtener_solicitud(id_solicitud)
    if not datos:
        raise ValueError(f"No existe la solicitud con id {id_solicitud}.")

    ruta = datos.get("ruta_pdf")
    if regenerar or not ruta or not Path(ruta).exists():
        ruta = generar_pdf_solicitud(id_solicitud)

    ruta = Path(ruta)
    return ruta, ruta.read_bytes()


def verificar_integridad_pdf(id_solicitud):
    """Compara el PDF actual con el sello SHA-256 registrado.

    Devuelve un diccionario con `estado` (ok, alterado, sin_sello, sin_pdf),
    la ruta, el sello esperado y el calculado.
    """
    datos = obtener_solicitud(id_solicitud)
    if not datos:
        raise ValueError(f"No existe la solicitud con id {id_solicitud}.")

    ruta = datos.get("ruta_pdf")
    esperado = datos.get("pdf_hash")
    resultado = {
        "estado": "sin_pdf",
        "ruta": ruta,
        "sello_esperado": esperado,
        "sello_actual": None,
    }

    if not ruta or not Path(ruta).exists():
        return resultado

    actual = calcular_sha256(ruta)
    resultado["sello_actual"] = actual

    if not esperado:
        resultado["estado"] = "sin_sello"
        return resultado

    resultado["estado"] = "ok" if actual == esperado else "alterado"
    return resultado
