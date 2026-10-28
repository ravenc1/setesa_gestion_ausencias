# Servicio del algoritmo de vigencia semestral (RF-05 / CU-06).
#
# Reglas:
#   1. Un usuario activo con más de 6 meses sin actividad pasa a baja lógica
#      (estado_vigencia = FALSE), sin borrar su historial.
#   2. Los roles administrativos nunca se desactivan automáticamente.
#   3. Cada ejecución y cada reactivación quedan auditadas en vigencia_log.
#   4. La actividad se actualiza en login y en cada escritura relevante.
#
# Este módulo no importa Streamlit: puede usarse desde la UI y desde la CLI.

import pandas as pd

from src.core.database import get_connection, get_engine
from src.core.logging_config import obtener_logger

logger = obtener_logger("setesa.vigencia")

MESES_VIGENCIA = 6
ROLES_PROTEGIDOS = ("Administrador",)

ACCION_DEPURACION = "DEPURACION"
ACCION_AUTOMATICA = "AUTOMATICA"
ACCION_REACTIVACION = "REACTIVACION"
ACCIONES_VALIDAS = (ACCION_DEPURACION, ACCION_AUTOMATICA, ACCION_REACTIVACION)


class UsuarioNoEncontrado(Exception):
    """No existe un usuario con el identificador indicado."""


def marcar_actividad(cursor, id_usuario):
    """Actualiza `ultima_actividad` usando un cursor existente (misma transacción)."""
    cursor.execute(
        "UPDATE usuario SET ultima_actividad = NOW() WHERE id_usuario = %s",
        (id_usuario,),
    )


def registrar_actividad(id_usuario):
    """Actualiza `ultima_actividad` en su propia transacción."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn:
            with conn.cursor() as cursor:
                marcar_actividad(cursor, id_usuario)
        return True
    finally:
        conn.close()


def usuario_activo(id_usuario):
    """Indica si el usuario sigue vigente. Ante fallo de BD no bloquea la sesión."""
    conn = get_connection()
    if not conn:
        return True
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT estado_vigencia FROM usuario WHERE id_usuario = %s",
                (id_usuario,),
            )
            fila = cursor.fetchone()
            return bool(fila and fila[0])
    finally:
        conn.close()


def _consulta_inactivos(id_excluido=None):
    # Los roles protegidos se expanden como parámetros escalares para que la
    # consulta funcione igual con psycopg2 y con SQLAlchemy (sin arrays).
    marcadores = ", ".join(["%s"] * len(ROLES_PROTEGIDOS))
    query = f"""
        SELECT u.id_usuario, u.nombre_completo, u.correo_institucional,
               u.ultima_actividad, r.nombre_rol
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.estado_vigencia = TRUE
          AND u.ultima_actividad < CURRENT_DATE - INTERVAL '6 months'
          AND r.nombre_rol NOT IN ({marcadores})
    """
    params = list(ROLES_PROTEGIDOS)
    if id_excluido is not None:
        query += " AND u.id_usuario <> %s"
        params.append(id_excluido)
    return query, tuple(params)


def obtener_inactivos(id_excluido=None):
    """Lista los usuarios que serían dados de baja (sin modificar nada)."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    query, params = _consulta_inactivos(id_excluido)
    return pd.read_sql_query(
        query + " ORDER BY u.ultima_actividad ASC", engine, params=params
    )


def obtener_dados_de_baja():
    """Lista los usuarios con baja lógica (estado_vigencia = FALSE)."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    query = """
        SELECT u.id_usuario, u.nombre_completo, u.correo_institucional,
               u.ultima_actividad, r.nombre_rol
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.estado_vigencia = FALSE
        ORDER BY u.ultima_actividad ASC
    """
    return pd.read_sql_query(query, engine)


def ejecutar_depuracion(id_ejecutor=None, accion=ACCION_DEPURACION):
    """Aplica baja lógica a los usuarios inactivos y registra la ejecución.

    Devuelve (DataFrame de afectados, id_log). La selección usa FOR UPDATE para
    evitar que dos ejecuciones concurrentes desactiven al mismo usuario.
    """
    if accion not in (ACCION_DEPURACION, ACCION_AUTOMATICA):
        raise ValueError(f"Acción de depuración inválida: {accion}")

    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                query, params = _consulta_inactivos(id_excluido=id_ejecutor)
                cursor.execute(
                    query + " ORDER BY u.ultima_actividad ASC FOR UPDATE OF u",
                    params,
                )
                filas = cursor.fetchall()

                columnas = [
                    "id_usuario",
                    "nombre_completo",
                    "correo_institucional",
                    "ultima_actividad",
                    "nombre_rol",
                ]
                df_afectados = pd.DataFrame(filas, columns=columnas)

                ids = [fila[0] for fila in filas]
                if ids:
                    cursor.execute(
                        "UPDATE usuario SET estado_vigencia = FALSE "
                        "WHERE id_usuario = ANY(%s)",
                        (ids,),
                    )

                detalle = (
                    "ids=" + ",".join(str(i) for i in ids)
                    if ids
                    else "sin afectados"
                )
                cursor.execute(
                    """
                    INSERT INTO vigencia_log
                        (id_ejecutor, accion, usuarios_afectados, detalle)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id_log
                    """,
                    (id_ejecutor, accion, len(ids), detalle),
                )
                id_log = cursor.fetchone()[0]

        logger.info(
            "Vigencia %s: %s usuario(s) afectado(s), log %s",
            accion,
            len(df_afectados),
            id_log,
        )
        return df_afectados, id_log
    finally:
        conn.close()


def reactivar_usuario(id_usuario, id_ejecutor=None):
    """Reactiva un usuario dado de baja y registra la acción. Devuelve id_log."""
    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT estado_vigencia FROM usuario WHERE id_usuario = %s FOR UPDATE",
                    (id_usuario,),
                )
                if not cursor.fetchone():
                    raise UsuarioNoEncontrado(
                        f"No existe el usuario con id {id_usuario}."
                    )

                cursor.execute(
                    """
                    UPDATE usuario
                    SET estado_vigencia = TRUE, ultima_actividad = NOW()
                    WHERE id_usuario = %s
                    """,
                    (id_usuario,),
                )
                cursor.execute(
                    """
                    INSERT INTO vigencia_log
                        (id_ejecutor, accion, usuarios_afectados, detalle)
                    VALUES (%s, %s, 1, %s)
                    RETURNING id_log
                    """,
                    (id_ejecutor, ACCION_REACTIVACION, f"id={id_usuario}"),
                )
                id_log = cursor.fetchone()[0]

        logger.info(
            "Reactivación del usuario %s (log %s)", id_usuario, id_log
        )
        return id_log
    finally:
        conn.close()


def debe_ejecutarse_automaticamente():
    """True si no hay una depuración registrada en los últimos 6 meses."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM vigencia_log
                WHERE accion IN (%s, %s)
                  AND fecha_ejecucion > NOW() - INTERVAL '6 months'
                LIMIT 1
                """,
                (ACCION_DEPURACION, ACCION_AUTOMATICA),
            )
            return cursor.fetchone() is None
    finally:
        conn.close()


def ejecutar_si_corresponde(id_ejecutor=None):
    """Ejecuta la depuración semestral si el periodo está vencido.

    Devuelve (cantidad_afectados, id_log) o None si aún no corresponde.
    """
    if not debe_ejecutarse_automaticamente():
        return None
    df_afectados, id_log = ejecutar_depuracion(
        id_ejecutor=id_ejecutor, accion=ACCION_AUTOMATICA
    )
    return len(df_afectados), id_log


def obtener_historial_vigencia(limite=10):
    """Devuelve las últimas ejecuciones/reactivaciones para el panel."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    query = """
        SELECT l.fecha_ejecucion, l.accion, l.usuarios_afectados,
               u.nombre_completo AS ejecutor, l.detalle
        FROM vigencia_log l
        LEFT JOIN usuario u ON l.id_ejecutor = u.id_usuario
        ORDER BY l.fecha_ejecucion DESC, l.id_log DESC
        LIMIT %s
    """
    return pd.read_sql_query(query, engine, params=(limite,))
