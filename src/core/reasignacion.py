# Fase 12: Gerencia reasigna expedientes a otro Coordinador GTC.
#
# Si un coordinador se da de baja (o deja de atender), sus expedientes que
# esperan el visto bueno del banco quedarían sin quien los firme. IT (que da de
# baja al coordinador saliente) o Gerencia los mueven a otro Coordinador GTC
# vigente. El estado no cambia: el
# movimiento queda en solicitud_historial con el motivo, y los recordatorios
# pendientes pasan al nuevo coordinador.

import pandas as pd

from src.core.cache import escritura, lectura
from src.core.database import get_connection, get_engine
from src.core.logging_config import obtener_logger
from src.core.vigencia import marcar_actividad
from src.core.workflow import ESTADO_PENDIENTE_FIRMA_COORDINADOR

logger = obtener_logger("setesa.reasignacion")


class ReasignacionError(Exception):
    """La reasignación no se puede aplicar."""


@lectura(ttl=15)
def listar_expedientes_reasignables():
    """Expedientes que esperan la firma del banco, con su coordinador actual.

    ``coordinador_vigente`` es False si el coordinador asignado fue dado de
    baja o si el expediente no tiene coordinador.
    """
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    query = """
        SELECT s.id_solicitud, u.nombre_completo AS consultor,
               s.tipo_ausencia, s.fecha_inicio, s.fecha_fin,
               s.id_coordinador,
               COALESCE(c.nombre_completo, s.jefe_gtc, 'Sin asignar')
                   AS coordinador,
               COALESCE(c.estado_vigencia, FALSE) AS coordinador_vigente,
               s.fecha_creacion
        FROM solicitud s
        JOIN usuario u ON s.id_usuario = u.id_usuario
        LEFT JOIN usuario c ON s.id_coordinador = c.id_usuario
        WHERE s.estado_workflow = %s
        ORDER BY coordinador_vigente ASC, s.fecha_creacion ASC
    """
    return pd.read_sql_query(
        query, engine, params=(ESTADO_PENDIENTE_FIRMA_COORDINADOR,)
    )


def contar_pendientes_coordinador(id_coordinador):
    """Expedientes que esperan la firma de ese coordinador."""
    conn = get_connection()
    if not conn:
        return 0
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FROM solicitud
                WHERE id_coordinador = %s AND estado_workflow = %s
                """,
                (id_coordinador, ESTADO_PENDIENTE_FIRMA_COORDINADOR),
            )
            return cursor.fetchone()[0]
    finally:
        conn.close()


def _coordinador_vigente(cursor, id_coordinador):
    cursor.execute(
        """
        SELECT u.nombre_completo, u.correo_institucional
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.id_usuario = %s
          AND r.nombre_rol = 'Coordinador GTC'
          AND u.estado_vigencia = TRUE
        """,
        (id_coordinador,),
    )
    return cursor.fetchone()


@escritura
def reasignar_coordinador(id_solicitud, id_nuevo, id_ejecutor, motivo):
    """Asigna el expediente a otro Coordinador GTC vigente.

    Solo aplica a expedientes en 'Pendiente de Firma Coordinador'. Devuelve
    un dict con el coordinador anterior y el nuevo, y la cantidad de
    recordatorios trasladados. Lanza ReasignacionError si no procede.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ReasignacionError("Indique el motivo de la reasignación.")
    if not id_nuevo:
        raise ReasignacionError("Seleccione el nuevo Coordinador GTC.")

    conn = get_connection()
    if not conn:
        raise ReasignacionError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT estado_workflow, id_coordinador, jefe_gtc
                    FROM solicitud
                    WHERE id_solicitud = %s
                    FOR UPDATE
                    """,
                    (id_solicitud,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise ReasignacionError(
                        f"No existe el expediente con id {id_solicitud}."
                    )
                estado, id_anterior, nombre_anterior = fila

                if estado != ESTADO_PENDIENTE_FIRMA_COORDINADOR:
                    raise ReasignacionError(
                        "Solo se reasignan expedientes que esperan el visto "
                        f"bueno del Coordinador GTC (estado actual: {estado})."
                    )
                if id_anterior == id_nuevo:
                    raise ReasignacionError(
                        "El expediente ya está asignado a ese coordinador."
                    )

                nuevo = _coordinador_vigente(cursor, id_nuevo)
                if not nuevo:
                    raise ReasignacionError(
                        "El usuario elegido no es un Coordinador GTC vigente."
                    )
                nombre_nuevo, correo_nuevo = nuevo

                cursor.execute(
                    """
                    UPDATE solicitud
                    SET id_coordinador = %s, jefe_gtc = %s
                    WHERE id_solicitud = %s
                    """,
                    (id_nuevo, nombre_nuevo, id_solicitud),
                )

                # R-11: los avisos sin atender pasan al nuevo coordinador.
                cursor.execute(
                    """
                    UPDATE recordatorio
                    SET id_destinatario = %s, correo_destino = %s
                    WHERE id_solicitud = %s AND atendido = FALSE
                    """,
                    (id_nuevo, correo_nuevo, id_solicitud),
                )
                recordatorios = cursor.rowcount

                cursor.execute(
                    """
                    INSERT INTO solicitud_historial
                        (id_solicitud, estado_anterior, estado_nuevo,
                         id_usuario, observacion)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        id_solicitud,
                        estado,
                        estado,
                        id_ejecutor,
                        f"Reasignada de {nombre_anterior or 'sin coordinador'} "
                        f"a {nombre_nuevo}. Motivo: {motivo}",
                    ),
                )

                marcar_actividad(cursor, id_ejecutor)

        logger.info(
            "Expediente %s reasignado de %s a %s por usuario %s",
            id_solicitud,
            id_anterior,
            id_nuevo,
            id_ejecutor,
        )
        return {
            "anterior": nombre_anterior,
            "nuevo": nombre_nuevo,
            "recordatorios": recordatorios,
        }
    finally:
        conn.close()
