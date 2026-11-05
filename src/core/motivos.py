# Fase 21: catálogo mantenible de motivos de ausencia (tesis 6.4.4: "lista
# controlada" con un responsable y un procedimiento de actualización).
#
# - Responsable: Gerencia (Administrador), igual que el catálogo de feriados.
# - Los 22 motivos de la plantilla oficial vienen sembrados: no se renombran ni
#   se eliminan; se pueden desactivar (excepto los que tienen regla propia).
# - Un motivo nuevo no tiene casilla en la hoja oficial: en el PDF se marca
#   «OTROS» y se escribe su nombre.
# - Desactivar un motivo lo quita de los formularios nuevos; las solicitudes
#   anteriores lo conservan.
# - VACACION (saldo de días) y SUSPENSIÓN IGSS (constancia obligatoria) tienen
#   reglas en el sistema y no se pueden desactivar.

import pandas as pd

from src.core.cache import escritura, lectura
from src.core.catalogos import OPCIONES_AUSENCIA
from src.core.database import get_connection, get_engine
from src.core.logging_config import obtener_logger

logger = obtener_logger("setesa.motivos")

NOMBRE_MAX = 50
PROTEGIDOS = ("VACACION", "SUSPENSIÓN IGSS")
ROL_RESPONSABLE = "Administrador"


class MotivoError(Exception):
    """Operación no válida sobre el catálogo de motivos."""


def normalizar_nombre(nombre):
    """Mayúsculas, espacios simples y longitud válida."""
    limpio = " ".join((nombre or "").split()).upper()
    if len(limpio) < 3:
        raise MotivoError("El nombre del motivo debe tener al menos 3 caracteres.")
    if len(limpio) > NOMBRE_MAX:
        raise MotivoError(f"El nombre admite como máximo {NOMBRE_MAX} caracteres.")
    return limpio


@lectura(ttl=60)
def listar_motivos(solo_activos=False):
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    query = (
        "SELECT id_motivo, nombre, activo, en_plantilla, protegido, fecha_creacion "
        "FROM motivo_ausencia"
    )
    if solo_activos:
        query += " WHERE activo = TRUE"
    return pd.read_sql_query(query + " ORDER BY id_motivo", engine)


def opciones_activas():
    """Motivos que se ofrecen en el formulario; si el catálogo no responde,
    la lista base de la plantilla."""
    try:
        df = listar_motivos(solo_activos=True)
        if not df.empty:
            return df["nombre"].tolist()
    except Exception as e:
        logger.warning("No se pudo leer el catálogo de motivos: %s", e)
    return list(OPCIONES_AUSENCIA)


def _validar_responsable(cursor, id_ejecutor):
    cursor.execute(
        """
        SELECT r.nombre_rol FROM usuario u JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.id_usuario = %s AND u.estado_vigencia = TRUE
        """,
        (id_ejecutor,),
    )
    fila = cursor.fetchone()
    if not fila or fila[0] != ROL_RESPONSABLE:
        raise MotivoError("Solo Gerencia puede mantener el catálogo de motivos.")


@escritura
def crear_motivo(id_ejecutor, nombre):
    """Agrega un motivo nuevo (activo). Devuelve su nombre normalizado."""
    nombre = normalizar_nombre(nombre)
    conn = get_connection()
    if not conn:
        raise MotivoError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                _validar_responsable(cursor, id_ejecutor)
                cursor.execute(
                    "SELECT 1 FROM motivo_ausencia WHERE UPPER(nombre) = %s",
                    (nombre,),
                )
                if cursor.fetchone():
                    raise MotivoError(f"Ya existe el motivo «{nombre}».")
                cursor.execute(
                    "INSERT INTO motivo_ausencia (nombre, id_creador) VALUES (%s, %s)",
                    (nombre, id_ejecutor),
                )
    finally:
        conn.close()
    logger.info("Motivo «%s» creado por usuario %s", nombre, id_ejecutor)
    return nombre


@escritura
def cambiar_estado_motivo(id_ejecutor, id_motivo, activo):
    """Activa o desactiva un motivo. Devuelve su nombre."""
    conn = get_connection()
    if not conn:
        raise MotivoError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                _validar_responsable(cursor, id_ejecutor)
                cursor.execute(
                    "SELECT nombre, protegido, activo FROM motivo_ausencia "
                    "WHERE id_motivo = %s FOR UPDATE",
                    (id_motivo,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise MotivoError("El motivo no existe.")
                nombre, protegido, actual = fila
                if not activo and protegido:
                    raise MotivoError(
                        f"«{nombre}» tiene una regla propia en el sistema y no "
                        "se puede desactivar."
                    )
                if actual == activo:
                    return nombre
                cursor.execute(
                    "UPDATE motivo_ausencia SET activo = %s WHERE id_motivo = %s",
                    (activo, id_motivo),
                )
    finally:
        conn.close()
    logger.info(
        "Motivo «%s» %s por usuario %s",
        nombre, "activado" if activo else "desactivado", id_ejecutor,
    )
    return nombre
