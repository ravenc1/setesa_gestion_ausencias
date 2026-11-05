# Envío de correo por SMTP con la cuenta de SETESA (Fase 15).
#
# Configuración (variables de entorno, .env o secretos de GitHub/Render):
#   SMTP_HOST        p. ej. smtp.gmail.com o smtp.office365.com
#   SMTP_PORT        587 (STARTTLS, por defecto) o 465 (SSL)
#   SMTP_USUARIO     cuenta que envía, p. ej. notificaciones@setesa.com
#   SMTP_PASSWORD    contraseña de aplicación de esa cuenta (nunca en el repo)
#   SMTP_REMITENTE   opcional; por defecto, SMTP_USUARIO
#
# Si falta la configuración, el sistema sigue funcionando: los avisos se
# muestran dentro de la app y el envío por correo queda desactivado.

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from src.core.config import obtener_variable

NOMBRE_REMITENTE = "SETESA - Sistema de Ausencias"
TIMEOUT_SEGUNDOS = 30


class CorreoError(Exception):
    """No se pudo enviar el correo."""


def configuracion_smtp():
    """Devuelve la configuración SMTP o None si está incompleta."""
    host = obtener_variable("SMTP_HOST")
    usuario = obtener_variable("SMTP_USUARIO")
    password = obtener_variable("SMTP_PASSWORD")
    if not (host and usuario and password):
        return None
    try:
        puerto = int(obtener_variable("SMTP_PORT") or 587)
    except ValueError as e:
        raise CorreoError("SMTP_PORT debe ser un número.") from e
    return {
        "host": host,
        "puerto": puerto,
        "usuario": usuario,
        "password": password,
        "remitente": obtener_variable("SMTP_REMITENTE") or usuario,
    }


def correo_configurado():
    return configuracion_smtp() is not None


def construir_mensaje(remitente, destinatario, asunto, cuerpo):
    mensaje = EmailMessage()
    mensaje["From"] = formataddr((NOMBRE_REMITENTE, remitente))
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    return mensaje


def enviar_correo(destinatario, asunto, cuerpo, config=None):
    """Envía un correo de texto. Lanza CorreoError si falla."""
    config = config or configuracion_smtp()
    if not config:
        raise CorreoError("El envío de correo no está configurado (SMTP_*).")

    mensaje = construir_mensaje(config["remitente"], destinatario, asunto, cuerpo)
    contexto = ssl.create_default_context()
    try:
        if config["puerto"] == 465:
            servidor = smtplib.SMTP_SSL(
                config["host"], config["puerto"],
                timeout=TIMEOUT_SEGUNDOS, context=contexto,
            )
        else:
            servidor = smtplib.SMTP(
                config["host"], config["puerto"], timeout=TIMEOUT_SEGUNDOS
            )
        with servidor:
            if config["puerto"] != 465:
                servidor.starttls(context=contexto)
            servidor.login(config["usuario"], config["password"])
            servidor.send_message(mensaje)
    except (smtplib.SMTPException, OSError) as e:
        raise CorreoError(f"No se pudo enviar el correo a {destinatario}: {e}") from e
