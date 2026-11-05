# Fase 25: avisos por correo del flujo de aprobación.
#
# Quien debe actuar se entera sin entrar a la plataforma:
#   NUEVA        -> Coordinador GTC asignado (solicitud nueva o por firmar).
#   VISTO_BUENO  -> Gerencia (expediente listo para aprobar o denegar).
#   RETIRADA     -> Coordinador GTC (el consultor retiró la solicitud).
#   FINALIZADA   -> consultor dueño y Contabilidad y RR.HH. (aprobada/denegada).
#
# Reglas:
#   - El correo es un AVISO: nunca incluye la explicación, el motivo de la
#     resolución ni firmas; solo número, persona, tipo y fechas.
#   - Es de mejor esfuerzo: si el correo no está configurado o falla, el flujo
#     sigue igual (todo queda en la plataforma) y solo se registra en el log.
#   - Se envía en segundo plano para no hacer esperar al usuario.

import os
import threading

from src.core.database import get_connection
from src.core.logging_config import obtener_logger
from src.services.correo import configuracion_smtp, enviar_correo

logger = obtener_logger("setesa.avisos_flujo")

NUEVA = "NUEVA"
VISTO_BUENO = "VISTO_BUENO"
RETIRADA = "RETIRADA"
FINALIZADA = "FINALIZADA"
EVENTOS = (NUEVA, VISTO_BUENO, RETIRADA, FINALIZADA)


def _deshabilitado():
    return bool(os.getenv("SETESA_SIN_CORREO"))


def _datos_solicitud(cursor, id_solicitud):
    cursor.execute(
        """
        SELECT s.id_solicitud, s.tipo_ausencia, s.fecha_inicio, s.fecha_fin,
               s.resolucion, s.id_coordinador, s.id_usuario,
               u.nombre_completo
        FROM solicitud s
        JOIN usuario u ON u.id_usuario = s.id_usuario
        WHERE s.id_solicitud = %s
        """,
        (id_solicitud,),
    )
    fila = cursor.fetchone()
    if not fila:
        return None
    columnas = (
        "id_solicitud", "tipo_ausencia", "fecha_inicio", "fecha_fin",
        "resolucion", "id_coordinador", "id_usuario", "nombre_completo",
    )
    return dict(zip(columnas, fila))


def _usuarios(cursor, ids=None, rol=None):
    """Correo y nombre de usuarios vigentes, por id o por rol."""
    if ids is not None:
        ids = [i for i in ids if i is not None]
        if not ids:
            return []
        cursor.execute(
            """
            SELECT correo_institucional, nombre_completo FROM usuario
            WHERE id_usuario = ANY(%s) AND COALESCE(estado_vigencia, TRUE)
            """,
            (ids,),
        )
    else:
        cursor.execute(
            """
            SELECT u.correo_institucional, u.nombre_completo FROM usuario u
            JOIN rol r ON r.id_rol = u.id_rol
            WHERE r.nombre_rol = %s AND COALESCE(u.estado_vigencia, TRUE)
            """,
            (rol,),
        )
    return [(c, n) for c, n in cursor.fetchall() if c]


def destinatarios(cursor, evento, datos):
    """Personas que reciben el aviso de ``evento``."""
    if evento in (NUEVA, RETIRADA):
        return _usuarios(cursor, ids=[datos["id_coordinador"]])
    if evento == VISTO_BUENO:
        return _usuarios(cursor, rol="Administrador")
    if evento == FINALIZADA:
        return _usuarios(cursor, ids=[datos["id_usuario"]]) + _usuarios(
            cursor, rol="Contabilidad"
        )
    return []


def _periodo(datos):
    return (
        f"{datos['tipo_ausencia']}, del {datos['fecha_inicio']:%d/%m/%Y} "
        f"al {datos['fecha_fin']:%d/%m/%Y}"
    )


def construir_aviso(evento, datos, nombre_destinatario=""):
    """Asunto y cuerpo del aviso (sin datos sensibles)."""
    numero = datos["id_solicitud"]
    persona = datos["nombre_completo"]
    detalle = f"Expediente #{numero} de {persona} ({_periodo(datos)})."
    saludo = f"Hola {nombre_destinatario}," if nombre_destinatario else "Hola,"

    if evento == NUEVA:
        asunto = f"Solicitud #{numero} pendiente de su visto bueno"
        accion = "Tiene una solicitud pendiente de su visto bueno en la plataforma."
    elif evento == VISTO_BUENO:
        asunto = f"Expediente #{numero} listo para la decisión de Gerencia"
        accion = (
            "El Coordinador GTC dio su visto bueno: el expediente espera su "
            "aprobación o denegación."
        )
    elif evento == RETIRADA:
        asunto = f"Solicitud #{numero} retirada por el consultor"
        accion = (
            "El consultor retiró esta solicitud; ya no requiere su visto bueno."
        )
    elif evento == FINALIZADA:
        resolucion = (datos.get("resolucion") or "finalizado").upper()
        asunto = f"Expediente #{numero}: {resolucion}"
        accion = f"El expediente fue resuelto: {resolucion}."
    else:
        raise ValueError(f"Evento de aviso desconocido: {evento}")

    cuerpo = (
        f"{saludo}\n\n{accion}\n{detalle}\n\n"
        "Ingrese a la plataforma SETESA para ver el detalle. Este mensaje es "
        "solo un aviso y no contiene datos del expediente más allá de los "
        "indicados."
    )
    return asunto, cuerpo


def avisar(evento, id_solicitud, enviar=enviar_correo):
    """Envía el aviso del evento. Nunca lanza: devuelve cuántos correos salieron."""
    if _deshabilitado():
        return 0
    try:
        config = configuracion_smtp()
        if not config:
            return 0
        conn = get_connection()
        if not conn:
            return 0
        try:
            with conn.cursor() as cursor:
                datos = _datos_solicitud(cursor, id_solicitud)
                if not datos:
                    return 0
                personas = destinatarios(cursor, evento, datos)
        finally:
            conn.close()

        enviados = 0
        for correo, nombre in personas:
            asunto, cuerpo = construir_aviso(evento, datos, nombre)
            try:
                enviar(correo, asunto, cuerpo, config=config)
                enviados += 1
            except Exception as e:  # el correo nunca debe romper el flujo
                logger.warning(
                    "No se pudo avisar (%s, expediente %s): %s",
                    evento, id_solicitud, e,
                )
        return enviados
    except Exception:
        logger.exception("Error al preparar el aviso %s del expediente %s",
                         evento, id_solicitud)
        return 0


def avisar_en_segundo_plano(evento, id_solicitud):
    """Lanza el aviso sin hacer esperar a quien actuó."""
    if _deshabilitado():
        return None
    hilo = threading.Thread(
        target=avisar, args=(evento, id_solicitud), daemon=True,
        name=f"aviso-{evento}-{id_solicitud}",
    )
    hilo.start()
    return hilo
