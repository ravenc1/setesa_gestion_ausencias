# Servicio de documentos oficiales.
#
# Genera el PDF de una solicitud a partir de los datos persistidos en la base
# (incluidas las firmas ya capturadas), lo guarda en el repositorio
# persistente (Fase 17: Supabase Storage) y registra su sello SHA-256 en
# `solicitud.pdf_hash` (H-13).
#
# Reglas del repositorio:
#   - Mientras el expediente está en trámite, el PDF es un borrador que se
#     puede regenerar (pdf/<id>/borrador.pdf).
#   - Al resolverse (Finalizada, Aprobada o Denegada) se genera UNA vez el PDF
#     final (pdf/<id>/final_<sello>.pdf), que queda inmutable: no se
#     regenera ni se sobrescribe, así su sello SHA-256 no cambia nunca.

import hashlib
from pathlib import Path

from src.core.logging_config import obtener_logger
from src.core.solicitudes import obtener_solicitud, registrar_pdf
from src.core.workflow import ESTADO_FINALIZADA
from src.services import almacenamiento
from src.services.motor_pdf import generar_pdf_accion_personal
from src.services.utils_firma import eliminar_archivo

logger = obtener_logger("setesa.documentos")

BLOQUE_LECTURA = 64 * 1024


class PDFNoDisponible(Exception):
    """El PDF final no está en el repositorio (posible pérdida o alteración)."""


def calcular_sha256(ruta):
    """Calcula el SHA-256 de un archivo por bloques."""
    digest = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(BLOQUE_LECTURA), b""):
            digest.update(bloque)
    return digest.hexdigest()


def sha256_bytes(contenido):
    return hashlib.sha256(contenido).hexdigest()


def clave_pdf(id_solicitud, final, sello=None):
    """Clave del PDF en el repositorio."""
    if final:
        return f"pdf/{id_solicitud}/final_{sello[:16]}.pdf"
    return f"pdf/{id_solicitud}/borrador.pdf"


def nombre_descarga(id_solicitud, final):
    sufijo = "final" if final else "borrador"
    return f"Accion_Personal_SETESA_{id_solicitud}_{sufijo}.pdf"


def _leer(clave):
    """Lee del repositorio; admite rutas locales de expedientes anteriores."""
    if clave and Path(clave).is_absolute():
        ruta = Path(clave)
        if not ruta.exists():
            raise almacenamiento.ArchivoNoEncontrado(f"No existe {clave}.")
        return ruta.read_bytes()
    return almacenamiento.leer(clave)


def _existe(clave):
    try:
        _leer(clave)
        return True
    except almacenamiento.ArchivoNoEncontrado:
        return False


def generar_pdf_solicitud(id_solicitud):
    """Genera, sella y guarda el PDF oficial del expediente.

    Devuelve la clave del PDF en el repositorio. Si el expediente ya tiene su
    PDF final inmutable, lo devuelve sin regenerarlo. Lanza ValueError si la
    solicitud no existe.
    """
    datos = obtener_solicitud(id_solicitud)
    if not datos:
        raise ValueError(f"No existe la solicitud con id {id_solicitud}.")
    if datos.get("resolucion") == "Retirada":
        raise ValueError(
            f"La solicitud {id_solicitud} fue retirada por el consultor y no "
            "tiene PDF oficial."
        )
    if datos.get("pdf_inmutable") and datos.get("ruta_pdf"):
        return datos["ruta_pdf"]

    resolucion = datos.get("resolucion")
    ruta_temporal = generar_pdf_accion_personal(
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
        resolucion=resolucion,
        motivo_resolucion=datos.get("motivo_resolucion"),
        denegada_por=(
            "Gerencia" if datos.get("firma_gerencia") else "Coordinador GTC"
        )
        if resolucion == "Denegada"
        else None,
    )
    try:
        contenido = Path(ruta_temporal).read_bytes()
    finally:
        # El disco del servidor es efímero: el original vive en el repositorio.
        eliminar_archivo(ruta_temporal)

    sello = sha256_bytes(contenido)
    final = datos["estado_workflow"] == ESTADO_FINALIZADA
    clave = clave_pdf(id_solicitud, final, sello)
    try:
        almacenamiento.guardar(clave, contenido, sobrescribir=not final)
    except almacenamiento.ArchivoExistente:
        # La clave final incluye el sello: si ya existe, es el mismo archivo.
        pass

    registrar_pdf(id_solicitud, clave, sello, final)
    logger.info(
        "PDF %s de la solicitud %s guardado (sha256=%s)",
        "final" if final else "borrador",
        id_solicitud,
        sello,
    )
    return clave


def preparar_pdf_descarga(id_solicitud, regenerar=False):
    """Devuelve (nombre_archivo, contenido) del PDF listo para descargar.

    Un borrador se genera si falta o si ``regenerar=True``. El PDF final nunca
    se regenera: si faltara del repositorio se lanza PDFNoDisponible.
    """
    datos = obtener_solicitud(id_solicitud)
    if not datos:
        raise ValueError(f"No existe la solicitud con id {id_solicitud}.")

    clave = datos.get("ruta_pdf")
    inmutable = bool(datos.get("pdf_inmutable"))
    if not inmutable and (regenerar or not clave or not _existe(clave)):
        clave = generar_pdf_solicitud(id_solicitud)
        datos = obtener_solicitud(id_solicitud)
        inmutable = bool(datos.get("pdf_inmutable"))

    try:
        contenido = _leer(clave)
    except almacenamiento.ArchivoNoEncontrado as e:
        raise PDFNoDisponible(
            f"El PDF final del expediente {id_solicitud} no está en el "
            "repositorio. Repórtelo a IT."
        ) from e
    return nombre_descarga(id_solicitud, inmutable), contenido


def verificar_integridad_pdf(id_solicitud):
    """Compara el PDF del repositorio con el sello SHA-256 registrado.

    Devuelve un diccionario con `estado` (ok, alterado, sin_sello, sin_pdf),
    la clave, el sello esperado y el calculado.
    """
    datos = obtener_solicitud(id_solicitud)
    if not datos:
        raise ValueError(f"No existe la solicitud con id {id_solicitud}.")

    clave = datos.get("ruta_pdf")
    esperado = datos.get("pdf_hash")
    resultado = {
        "estado": "sin_pdf",
        "ruta": clave,
        "sello_esperado": esperado,
        "sello_actual": None,
        "inmutable": bool(datos.get("pdf_inmutable")),
    }
    if not clave:
        return resultado
    try:
        contenido = _leer(clave)
    except almacenamiento.ArchivoNoEncontrado:
        return resultado

    actual = sha256_bytes(contenido)
    resultado["sello_actual"] = actual
    if not esperado:
        resultado["estado"] = "sin_sello"
    else:
        resultado["estado"] = "ok" if actual == esperado else "alterado"
    return resultado


def obtener_pdf_final_verificado(id_solicitud):
    """Devuelve (nombre, contenido, integridad) descargando el PDF una sola vez.

    ``integridad`` tiene la misma forma que ``verificar_integridad_pdf``. Como el
    PDF final es inmutable, la pantalla puede guardar este resultado un rato.
    """
    nombre, contenido = preparar_pdf_descarga(id_solicitud)
    datos = obtener_solicitud(id_solicitud)
    esperado = datos.get("pdf_hash")
    actual = sha256_bytes(contenido)
    if not esperado:
        estado = "sin_sello"
    else:
        estado = "ok" if actual == esperado else "alterado"
    return nombre, contenido, {
        "estado": estado,
        "ruta": datos.get("ruta_pdf"),
        "sello_esperado": esperado,
        "sello_actual": actual,
        "inmutable": bool(datos.get("pdf_inmutable")),
    }
