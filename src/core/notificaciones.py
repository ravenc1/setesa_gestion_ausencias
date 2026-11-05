# Fase 18: avisos dentro del sistema (tesis 4.12.3 paso 6 y figura 44).
#
# Cuando un expediente se finaliza (Aprobada o Denegada), el trigger
# trg_solicitud_notificar crea un aviso para cada usuario vigente de
# Contabilidad y RR.HH. y para el consultor dueño. El aviso no incluye el
# motivo de la resolución (puede ser sensible). Desde el aviso se puede abrir
# un correo prellenado (mailto) al consultor.

import pandas as pd

from src.core.database import get_connection, get_engine
from src.core.recordatorios import construir_enlace_correo


def contar_no_leidas(id_usuario):
    conn = get_connection()
    if not conn:
        return 0
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM notificacion "
                "WHERE id_destinatario = %s AND leida = FALSE",
                (id_usuario,),
            )
            return cursor.fetchone()[0]
    finally:
        conn.close()


def listar_notificaciones(id_usuario, limite=100):
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT n.id_notificacion, n.fecha, n.mensaje, n.leida, n.id_solicitud,
               u.nombre_completo AS consultor,
               u.correo_institucional AS correo_consultor
        FROM notificacion n
        JOIN solicitud s ON s.id_solicitud = n.id_solicitud
        JOIN usuario u ON u.id_usuario = s.id_usuario
        WHERE n.id_destinatario = %s
        ORDER BY n.leida ASC, n.fecha DESC, n.id_notificacion DESC
        LIMIT %s
        """,
        engine,
        params=(id_usuario, limite),
    )


def marcar_leidas(id_usuario, ids=None):
    """Marca como leídas las notificaciones del usuario (todas o ``ids``)."""
    conn = get_connection()
    if not conn:
        return 0
    try:
        with conn:
            with conn.cursor() as cursor:
                if ids:
                    cursor.execute(
                        "UPDATE notificacion SET leida = TRUE "
                        "WHERE id_destinatario = %s AND leida = FALSE "
                        "AND id_notificacion = ANY(%s)",
                        (id_usuario, list(ids)),
                    )
                else:
                    cursor.execute(
                        "UPDATE notificacion SET leida = TRUE "
                        "WHERE id_destinatario = %s AND leida = FALSE",
                        (id_usuario,),
                    )
                return cursor.rowcount
    finally:
        conn.close()


def enlace_al_consultor(fila):
    """Correo prellenado al consultor sobre la resolución de su expediente."""
    return construir_enlace_correo(
        fila["correo_consultor"],
        f"SETESA: resolución del expediente #{fila['id_solicitud']}",
        f"Estimado(a) {fila['consultor']}:\n\n{fila['mensaje']}\n\n"
        "Puede descargar el documento oficial desde el sistema de ausencias.\n\n"
        "SETESA - Contabilidad y RR.HH.",
    )
