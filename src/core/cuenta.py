# Fase 24: cambio de contraseña por el propio usuario.
#
# IT restablece la contraseña y entrega una TEMPORAL; la cuenta queda marcada
# (`debe_cambiar_password`) y, al iniciar sesión, el usuario debe elegir una
# propia antes de usar el sistema. Cualquier usuario puede además cambiarla
# cuando quiera desde «Mi contraseña».
#
# Para que la pantalla no sirva para adivinar la contraseña actual, los
# intentos fallidos cuentan para el mismo bloqueo del inicio de sesión.

from src.core import intentos
from src.core.cache import escritura
from src.core.database import get_connection
from src.core.gestion_usuarios import DatosInvalidos, validar_password
from src.core.logging_config import obtener_logger
from src.core.security import hash_password, verify_or_upgrade

logger = obtener_logger("setesa.cuenta")

ACCION_CAMBIO_PASSWORD = "CAMBIO_PASSWORD"


class PasswordError(Exception):
    """El cambio de contraseña no se puede aplicar."""


def requiere_cambio(id_usuario):
    """True si el usuario debe cambiar su contraseña antes de continuar."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(debe_cambiar_password, FALSE) FROM usuario "
                "WHERE id_usuario = %s",
                (id_usuario,),
            )
            fila = cursor.fetchone()
            return bool(fila and fila[0])
    finally:
        conn.close()


@escritura
def cambiar_password(id_usuario, actual, nueva, confirmacion):
    """Cambia la contraseña tras verificar la actual. Lanza PasswordError."""
    if nueva != confirmacion:
        raise PasswordError("La contraseña nueva y su confirmación no coinciden.")
    try:
        nueva = validar_password(nueva)
    except DatosInvalidos as e:
        raise PasswordError(str(e)) from e
    if nueva == actual:
        raise PasswordError("La contraseña nueva debe ser distinta de la actual.")

    conn = get_connection()
    if not conn:
        raise PasswordError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT password_hash, correo_institucional FROM usuario "
                    "WHERE id_usuario = %s FOR UPDATE",
                    (id_usuario,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise PasswordError("No existe el usuario.")
                guardada, correo = fila

                minutos = intentos.minutos_restantes(cursor, correo)
                if minutos:
                    raise PasswordError(str(intentos.CuentaBloqueada(minutos)))

                valida, _ = verify_or_upgrade(actual or "", guardada)
                if not valida:
                    intentos.registrar_fallo(cursor, correo)
                    # Se confirma el conteo aunque el cambio falle.
                    conn.commit()
                    raise PasswordError("La contraseña actual no es correcta.")

                cursor.execute(
                    "UPDATE usuario SET password_hash = %s, "
                    "debe_cambiar_password = FALSE WHERE id_usuario = %s",
                    (hash_password(nueva), id_usuario),
                )
                intentos.limpiar(cursor, correo)
                cursor.execute(
                    "INSERT INTO usuario_log (id_ejecutor, id_afectado, accion, detalle) "
                    "VALUES (%s, %s, %s, %s)",
                    (id_usuario, id_usuario, ACCION_CAMBIO_PASSWORD,
                     "Contraseña cambiada por el propio usuario"),
                )
    finally:
        conn.close()
    logger.info("Usuario %s cambió su contraseña", id_usuario)
