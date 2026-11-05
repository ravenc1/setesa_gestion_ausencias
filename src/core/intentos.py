# Fase 20: límite de intentos de acceso (OWASP: autenticación y fuerza bruta).
#
# Tras MAX_INTENTOS contraseñas incorrectas seguidas para un mismo correo, el
# acceso a esa cuenta se bloquea MINUTOS_BLOQUEO minutos. El conteo vive en la
# base (tabla intento_login), no en la sesión de Streamlit, así que abrir otra
# pestaña o navegador no lo reinicia. Se lleva por correo escrito, exista o no
# la cuenta, para que la respuesta no revele qué correos están registrados.

from src.core.config import soporte_correo
from src.core.logging_config import obtener_logger

logger = obtener_logger("setesa.intentos")

MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15


class CuentaBloqueada(Exception):
    """El acceso está bloqueado temporalmente por intentos fallidos."""

    def __init__(self, minutos):
        self.minutos = minutos
        super().__init__(
            "Demasiados intentos fallidos. Por seguridad, el acceso está "
            f"bloqueado; se libera solo en {minutos} minuto(s) o puede pedir a "
            f"IT que lo desbloquee ({soporte_correo()})."
        )


def normalizar(correo):
    return (correo or "").strip().lower()[:150]


def minutos_restantes(cursor, correo):
    """Minutos de bloqueo que faltan (0 si el acceso no está bloqueado)."""
    cursor.execute(
        """
        SELECT CEIL(EXTRACT(EPOCH FROM (bloqueado_hasta - NOW())) / 60)
        FROM intento_login
        WHERE correo = %s AND bloqueado_hasta > NOW()
        """,
        (normalizar(correo),),
    )
    fila = cursor.fetchone()
    return int(fila[0]) if fila and fila[0] else 0


def registrar_fallo(cursor, correo):
    """Suma un intento fallido; bloquea al llegar al máximo.

    Devuelve los intentos acumulados. La ventana de conteo es la misma del
    bloqueo: si el último fallo fue hace más de MINUTOS_BLOQUEO, se reinicia.
    """
    correo = normalizar(correo)
    cursor.execute(
        """
        INSERT INTO intento_login (correo, intentos, ultimo_intento)
        VALUES (%s, 1, NOW())
        ON CONFLICT (correo) DO UPDATE
            SET intentos = CASE
                    WHEN intento_login.ultimo_intento
                         < NOW() - (%s * INTERVAL '1 minute')
                    THEN 1
                    ELSE intento_login.intentos + 1
                END,
                ultimo_intento = NOW(),
                bloqueado_hasta = NULL
        RETURNING intentos
        """,
        (correo, MINUTOS_BLOQUEO),
    )
    intentos = cursor.fetchone()[0]
    if intentos >= MAX_INTENTOS:
        cursor.execute(
            """
            UPDATE intento_login
            SET bloqueado_hasta = NOW() + (%s * INTERVAL '1 minute')
            WHERE correo = %s
            """,
            (MINUTOS_BLOQUEO, correo),
        )
        logger.warning(
            "Acceso bloqueado %s min tras %s intentos fallidos (%s)",
            MINUTOS_BLOQUEO, intentos, correo,
        )
    return intentos


def limpiar(cursor, correo):
    """Borra el conteo (acceso correcto o desbloqueo por IT)."""
    cursor.execute(
        "DELETE FROM intento_login WHERE correo = %s", (normalizar(correo),)
    )
    return cursor.rowcount
