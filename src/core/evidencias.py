# Fase 18: evidencias adjuntas a la solicitud (tesis: "Carga de evidencias").
#
# Reglas:
#   - Opcionales; obligatorias (al menos una) en SUSPENSIÓN IGSS.
#   - PDF, JPG o PNG de hasta 5 MB; el tipo se verifica por el contenido, no
#     solo por la extensión.
#   - Se guardan en el bucket privado (evidencias/<uuid>.<ext>) y no se
#     modifican ni se borran (trigger).
#   - Las ven el consultor dueño, Contabilidad y RR.HH. y Gerencia; el
#     Coordinador GTC del banco no.

import hashlib
import uuid

import pandas as pd

from src.core.cache import escritura, lectura
from src.core.database import get_connection, get_engine
from src.core.logging_config import obtener_logger
from src.services import almacenamiento

logger = obtener_logger("setesa.evidencias")

TAMANO_MAXIMO = 5 * 1024 * 1024
TIPO_IGSS = "SUSPENSIÓN IGSS"
ROLES_CON_ACCESO = ("Administrador", "Contabilidad")

# Firma de bytes iniciales -> (tipo MIME, extensión)
_FIRMAS = (
    (b"%PDF", ("application/pdf", "pdf")),
    (b"\x89PNG\r\n\x1a\n", ("image/png", "png")),
    (b"\xff\xd8\xff", ("image/jpeg", "jpg")),
)
_EXTENSIONES = {"pdf": "pdf", "png": "png", "jpg": "jpg", "jpeg": "jpg"}


class EvidenciaError(Exception):
    """La evidencia no es válida o no se puede consultar."""


def evidencia_obligatoria(tipo_ausencia):
    return tipo_ausencia == TIPO_IGSS


def validar_archivo(nombre, contenido):
    """Devuelve (tipo_mime, extension) o lanza EvidenciaError."""
    nombre = (nombre or "").strip()
    if not nombre or not contenido:
        raise EvidenciaError("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise EvidenciaError(f"«{nombre}» supera el máximo de 5 MB.")
    extension = _EXTENSIONES.get(nombre.rsplit(".", 1)[-1].lower() if "." in nombre else "")
    if not extension:
        raise EvidenciaError(f"«{nombre}»: solo se aceptan PDF, JPG o PNG.")
    for firma, (tipo, ext_real) in _FIRMAS:
        if contenido.startswith(firma):
            if ext_real != extension:
                raise EvidenciaError(
                    f"«{nombre}»: el contenido no coincide con su extensión."
                )
            return tipo, ext_real
    raise EvidenciaError(f"«{nombre}» no es un PDF, JPG o PNG válido.")


def subir_evidencias(archivos):
    """Valida y sube los archivos al repositorio.

    ``archivos``: lista de (nombre, bytes). Devuelve la lista de metadatos que
    luego se registra en la base junto con la solicitud.
    """
    validados = [(nombre, contenido, *validar_archivo(nombre, contenido))
                 for nombre, contenido in archivos]
    subidos = []
    for nombre, contenido, tipo, extension in validados:
        clave = f"evidencias/{uuid.uuid4().hex}.{extension}"
        almacenamiento.guardar(clave, contenido, tipo=tipo, sobrescribir=False)
        subidos.append({
            "nombre_original": nombre[:255],
            "clave": clave,
            "tipo_mime": tipo,
            "tamano": len(contenido),
            "sha256": hashlib.sha256(contenido).hexdigest(),
        })
    return subidos


def insertar_evidencias(cursor, id_solicitud, id_usuario, evidencias):
    """Registra los metadatos dentro de una transacción existente."""
    for ev in evidencias or []:
        cursor.execute(
            """
            INSERT INTO evidencia
                (id_solicitud, id_usuario, nombre_original, clave,
                 tipo_mime, tamano, sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                id_solicitud,
                id_usuario,
                ev["nombre_original"],
                ev["clave"],
                ev["tipo_mime"],
                ev["tamano"],
                ev["sha256"],
            ),
        )


@escritura
def agregar_evidencias(id_solicitud, id_usuario, archivos):
    """Adjunta evidencias a una solicitud en trámite del propio consultor."""
    evidencias = subir_evidencias(archivos)
    conn = get_connection()
    if not conn:
        raise EvidenciaError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                insertar_evidencias(cursor, id_solicitud, id_usuario, evidencias)
    finally:
        conn.close()
    logger.info(
        "%s evidencia(s) agregadas a la solicitud %s", len(evidencias), id_solicitud
    )
    return len(evidencias)


def _puede_ver(cursor, id_solicitud, id_usuario):
    cursor.execute(
        """
        SELECT s.id_usuario, r.nombre_rol
        FROM solicitud s
        JOIN usuario u ON u.id_usuario = %s
        JOIN rol r ON r.id_rol = u.id_rol
        WHERE s.id_solicitud = %s
        """,
        (id_usuario, id_solicitud),
    )
    fila = cursor.fetchone()
    if not fila:
        return False
    dueno, rol = fila
    return dueno == id_usuario or rol in ROLES_CON_ACCESO


@lectura(ttl=15)
def listar_evidencias(id_solicitud, id_usuario):
    """Evidencias de la solicitud, si el usuario puede verlas."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()
    try:
        with conn.cursor() as cursor:
            if not _puede_ver(cursor, id_solicitud, id_usuario):
                raise EvidenciaError(
                    "No tiene permiso para ver las evidencias de este expediente."
                )
    finally:
        conn.close()

    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT id_evidencia, nombre_original, tipo_mime, tamano, fecha
        FROM evidencia
        WHERE id_solicitud = %s
        ORDER BY fecha, id_evidencia
        """,
        engine,
        params=(id_solicitud,),
    )


def descargar_evidencia(id_evidencia, id_usuario):
    """Devuelve (nombre, tipo, bytes) verificando permiso e integridad."""
    conn = get_connection()
    if not conn:
        raise EvidenciaError("No hay conexión a la base de datos.")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id_solicitud, nombre_original, tipo_mime, clave, sha256
                FROM evidencia WHERE id_evidencia = %s
                """,
                (id_evidencia,),
            )
            fila = cursor.fetchone()
            if not fila:
                raise EvidenciaError("La evidencia no existe.")
            id_solicitud, nombre, tipo, clave, sello = fila
            if not _puede_ver(cursor, id_solicitud, id_usuario):
                raise EvidenciaError(
                    "No tiene permiso para ver las evidencias de este expediente."
                )
    finally:
        conn.close()

    contenido = almacenamiento.leer(clave)
    if hashlib.sha256(contenido).hexdigest() != sello:
        raise EvidenciaError(f"«{nombre}» no coincide con su sello: fue alterada.")
    return nombre, tipo, contenido
