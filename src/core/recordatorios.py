# R-11: recordatorios del consultor al Coordinador GTC.
#
# El recordatorio no cambia el estado del workflow: es un aviso auditable que
# aparece en la bandeja del Coordinador y que, además, puede abrirse como un
# correo prellenado hacia su correo registrado (enlace mailto). No se envía
# correo automático porque el sistema no depende de un servidor SMTP.

from urllib.parse import quote

import pandas as pd

from src.core.crypto import cifrar, descifrar_dataframe
from src.core.database import get_connection, get_engine
from src.core.logging_config import obtener_logger
from src.core.workflow import ESTADO_PENDIENTE_FIRMA_COORDINADOR

logger = obtener_logger("setesa.recordatorios")

# Un expediente no puede generar más de un recordatorio por día.
HORAS_COOLDOWN = 24


class RecordatorioError(Exception):
    """Error controlado al registrar o consultar recordatorios."""


class RecordatorioReciente(RecordatorioError):
    """Ya existe un recordatorio del mismo expediente dentro del cooldown."""

    def __init__(self, disponible):
        self.disponible = disponible
        super().__init__(
            "Ya se envió un recordatorio para este expediente. "
            f"Podrá enviar otro a partir del {disponible:%d/%m/%Y %H:%M}."
        )


class RecordatorioNoPermitido(RecordatorioError):
    """El emisor o el estado del expediente no permiten el recordatorio."""


class SinCoordinador(RecordatorioError):
    """No hay un Coordinador GTC vigente al que dirigir el recordatorio."""


def _resolver_destinatario(cursor, jefe_gtc):
    """Devuelve el Coordinador GTC asignado o, en su defecto, el primero vigente.

    ``solicitud.jefe_gtc`` guarda el nombre visible del jefe inmediato. Si ese
    nombre ya no coincide con un usuario vigente, se usa el primer coordinador
    activo para no dejar el recordatorio sin destinatario.
    """
    cursor.execute(
        """
        SELECT u.id_usuario, u.nombre_completo, u.correo_institucional
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE r.nombre_rol = 'Coordinador GTC'
          AND u.estado_vigencia = TRUE
        ORDER BY (u.nombre_completo = %s) DESC, u.nombre_completo ASC
        LIMIT 1
        """,
        (jefe_gtc or "",),
    )
    return cursor.fetchone()


def registrar_recordatorio(id_solicitud, id_emisor, mensaje=None):
    """Registra un recordatorio del consultor dueño del expediente.

    Solo se permite mientras la solicitud espera la firma del Coordinador GTC.
    Devuelve los datos del envío (destinatario, correo, mensaje y fecha) o
    lanza una excepción controlada de ``RecordatorioError``.
    """
    conn = get_connection()
    if not conn:
        raise RecordatorioError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                # El bloqueo evita duplicados si el consultor pulsa dos veces.
                cursor.execute(
                    """
                    SELECT id_usuario, estado_workflow, jefe_gtc,
                           tipo_ausencia, fecha_inicio, fecha_fin
                    FROM solicitud
                    WHERE id_solicitud = %s
                    FOR UPDATE
                    """,
                    (id_solicitud,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise RecordatorioError(
                        f"No existe el expediente con id {id_solicitud}."
                    )

                id_dueno, estado, jefe, tipo, fecha_ini, fecha_fin = fila
                if id_dueno != id_emisor:
                    raise RecordatorioNoPermitido(
                        "Solo el consultor dueño del expediente puede enviar "
                        "el recordatorio."
                    )
                if estado != ESTADO_PENDIENTE_FIRMA_COORDINADOR:
                    raise RecordatorioNoPermitido(
                        "El recordatorio solo está disponible cuando el "
                        "expediente espera la firma del Coordinador GTC."
                    )

                # Cooldown calculado en la base para no depender de zonas horarias.
                cursor.execute(
                    """
                    SELECT fecha + (%s * INTERVAL '1 hour')
                    FROM recordatorio
                    WHERE id_solicitud = %s
                      AND fecha + (%s * INTERVAL '1 hour') > NOW()
                    ORDER BY fecha DESC
                    LIMIT 1
                    """,
                    (HORAS_COOLDOWN, id_solicitud, HORAS_COOLDOWN),
                )
                reciente = cursor.fetchone()
                if reciente:
                    raise RecordatorioReciente(reciente[0])

                destinatario = _resolver_destinatario(cursor, jefe)
                if not destinatario:
                    raise SinCoordinador(
                        "No hay un Coordinador GTC vigente registrado para "
                        "recibir el recordatorio."
                    )
                id_destinatario, nombre_destinatario, correo_destino = destinatario

                texto = (mensaje or "").strip()
                if not texto:
                    texto = (
                        f"Estimado Coordinador GTC: el expediente "
                        f"#{id_solicitud} ({tipo}, del "
                        f"{fecha_ini:%d/%m/%Y} al {fecha_fin:%d/%m/%Y}) está "
                        "pendiente de su visto bueno en la plataforma SETESA. "
                        "Agradecemos su gestión."
                    )

                cursor.execute(
                    """
                    INSERT INTO recordatorio
                        (id_solicitud, id_emisor, id_destinatario,
                         correo_destino, mensaje)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id_recordatorio, fecha
                    """,
                    (
                        id_solicitud,
                        id_emisor,
                        id_destinatario,
                        correo_destino,
                        # RNF-01: el mensaje puede contener datos del caso.
                        cifrar(texto),
                    ),
                )
                id_recordatorio, fecha = cursor.fetchone()

        logger.info(
            "Recordatorio %s del expediente %s enviado por usuario %s a %s",
            id_recordatorio,
            id_solicitud,
            id_emisor,
            nombre_destinatario,
        )
        return {
            "id_recordatorio": id_recordatorio,
            "id_destinatario": id_destinatario,
            "destinatario": nombre_destinatario,
            "correo": correo_destino,
            "mensaje": texto,
            "fecha": fecha,
        }
    finally:
        conn.close()


def obtener_recordatorios_pendientes(id_destinatario):
    """Recordatorios aún no atendidos de un Coordinador GTC."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    query = """
        SELECT r.id_recordatorio, r.id_solicitud, s.tipo_ausencia,
               u.nombre_completo AS consultor, r.fecha, r.mensaje,
               r.correo_destino
        FROM recordatorio r
        JOIN solicitud s ON r.id_solicitud = s.id_solicitud
        JOIN usuario u ON r.id_emisor = u.id_usuario
        WHERE r.atendido = FALSE
          AND r.id_destinatario = %s
        ORDER BY r.fecha DESC, r.id_recordatorio DESC
    """
    df = pd.read_sql_query(query, engine, params=(id_destinatario,))
    # RNF-01: el mensaje se guarda cifrado; se descifra solo al mostrarlo.
    return descifrar_dataframe(df, columnas=["mensaje"])


def ultimo_recordatorio(id_solicitud):
    """Último recordatorio de un expediente, para mostrarlo en el historial."""
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.fecha, r.atendido, r.correo_destino,
                       u.nombre_completo AS destinatario
                FROM recordatorio r
                LEFT JOIN usuario u ON r.id_destinatario = u.id_usuario
                WHERE r.id_solicitud = %s
                ORDER BY r.fecha DESC, r.id_recordatorio DESC
                LIMIT 1
                """,
                (id_solicitud,),
            )
            fila = cursor.fetchone()
            if not fila:
                return None
            return {
                "fecha": fila[0],
                "atendido": fila[1],
                "correo_destino": fila[2],
                "destinatario": fila[3],
            }
    finally:
        conn.close()


def marcar_atendidos(cursor, id_solicitud):
    """Marca como atendidos los recordatorios del expediente.

    Se ejecuta dentro de la misma transacción del cambio de estado. La
    comprobación de existencia permite actualizar el código antes de correr la
    migración sin romper las aprobaciones.
    """
    cursor.execute("SELECT to_regclass('public.recordatorio')")
    if cursor.fetchone()[0] is None:
        return 0
    cursor.execute(
        """
        UPDATE recordatorio
        SET atendido = TRUE, fecha_atencion = NOW()
        WHERE id_solicitud = %s AND atendido = FALSE
        """,
        (id_solicitud,),
    )
    return cursor.rowcount


def construir_enlace_correo(correo, asunto, cuerpo):
    """Arma un enlace ``mailto:`` con asunto y cuerpo prellenados."""
    return "mailto:{}?subject={}&body={}".format(
        quote(correo or "", safe="@"),
        quote(asunto, safe=""),
        quote(cuerpo, safe=""),
    )
