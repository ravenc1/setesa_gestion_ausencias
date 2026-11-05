# Fase 15: recordatorios por correo para actualizar "Mis datos".
#
# Una tarea diaria (GitHub Actions, scripts/enviar_recordatorios.py) revisa a
# los Consultores y a Contabilidad y RR.HH. vigentes cuyo plazo de 6 meses
# vence pronto y les escribe desde la cuenta de SETESA:
#
#   30, 15, 7 y 1 día(s) antes del vencimiento (un correo por etapa).
#
# Cada envío queda en aviso_actualizacion; así un mismo aviso no se repite
# aunque la tarea corra varias veces, y si un día no corre, al siguiente se
# envía el de la etapa en curso (no se acumulan correos atrasados). Cuando el
# usuario actualiza sus datos, cambia su fecha límite y el ciclo empieza otra vez.

import datetime

from src.core.config import obtener_variable
from src.core.database import get_connection
from src.core.logging_config import obtener_logger
from src.core.perfil import fecha_limite
from src.core.vigencia import ROLES_CON_ACTUALIZACION
from src.services.correo import CorreoError, configuracion_smtp, enviar_correo

logger = obtener_logger("setesa.avisos")

UMBRALES = (30, 15, 7, 1)
ESTADO_ENVIADO = "ENVIADO"
ESTADO_ERROR = "ERROR"

NOMBRES_ROL = {
    "Consultor": "Consultor",
    "Contabilidad": "Contabilidad y RR.HH.",
}


def umbral_aplicable(dias_restantes):
    """Etapa de aviso que corresponde, o None si no toca avisar."""
    if dias_restantes is None or dias_restantes < 0:
        return None
    for umbral in sorted(UMBRALES):
        if dias_restantes <= umbral:
            return umbral
    return None


def planificar_avisos(usuarios, hoy=None):
    """Elige qué usuarios reciben correo hoy.

    ``usuarios``: dicts con id_usuario, nombre_completo, correo_institucional,
    nombre_rol, fecha_actualizacion_datos y ``enviados`` (umbrales ya enviados
    para su fecha límite actual).
    """
    hoy = hoy or datetime.date.today()
    avisos = []
    for usuario in usuarios:
        limite = fecha_limite(usuario["fecha_actualizacion_datos"])
        dias = (limite - hoy).days
        umbral = umbral_aplicable(dias)
        if umbral is None or umbral in usuario.get("enviados", set()):
            continue
        avisos.append({**usuario, "fecha_limite": limite, "dias": dias, "umbral": umbral})
    return avisos


def redactar(aviso, url_app=None):
    """Asunto y cuerpo del correo de recordatorio."""
    limite = f"{aviso['fecha_limite']:%d/%m/%Y}"
    if aviso["dias"] <= 1:
        cuando = "vence mañana" if aviso["dias"] == 1 else "vence hoy"
        asunto = f"URGENTE - SETESA: su plazo para actualizar datos {cuando}"
    else:
        cuando = f"vence en {aviso['dias']} días"
        asunto = f"SETESA: actualice sus datos antes del {limite}"

    rol = NOMBRES_ROL.get(aviso["nombre_rol"], aviso["nombre_rol"])
    acceso = (
        f"Ingrese aquí: {url_app}\n" if url_app else
        "Ingrese al sistema de ausencias de SETESA.\n"
    )
    cuerpo = (
        f"Estimado(a) {aviso['nombre_completo']}:\n\n"
        f"Su plazo para actualizar sus datos ({rol}) en el sistema de "
        f"ausencias de SETESA {cuando}, el {limite}.\n\n"
        "Para mantener su cuenta activa:\n"
        f"  1. {acceso}"
        "  2. Abra «Mis datos» en el menú lateral.\n"
        "  3. Revise su información y pulse «Confirmar y actualizar mis datos».\n\n"
        "Si no actualiza sus datos antes de esa fecha, su cuenta pasará a baja "
        "lógica y deberá solicitar a IT su reactivación.\n\n"
        "Este es un mensaje automático; no responda a este correo.\n"
        "SETESA - Departamento de RR.HH."
    )
    return asunto, cuerpo


def _obtener_candidatos(cursor):
    """Usuarios vigentes con plazo en los próximos 30 días y avisos ya enviados."""
    marcadores = ", ".join(["%s"] * len(ROLES_CON_ACTUALIZACION))
    cursor.execute(
        f"""
        SELECT u.id_usuario, u.nombre_completo, u.correo_institucional,
               r.nombre_rol, u.fecha_actualizacion_datos,
               COALESCE(array_agg(a.umbral) FILTER (WHERE a.umbral IS NOT NULL),
                        '{{}}') AS enviados
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        LEFT JOIN aviso_actualizacion a
               ON a.id_usuario = u.id_usuario
              AND a.fecha_limite = (u.fecha_actualizacion_datos
                                    + INTERVAL '6 months')::date
              AND a.estado = %s
        WHERE u.estado_vigencia = TRUE
          AND r.nombre_rol IN ({marcadores})
          AND (u.fecha_actualizacion_datos + INTERVAL '6 months')::date
              BETWEEN CURRENT_DATE AND CURRENT_DATE + %s
        GROUP BY u.id_usuario, r.nombre_rol
        """,
        (ESTADO_ENVIADO, *ROLES_CON_ACTUALIZACION, max(UMBRALES)),
    )
    columnas = [d[0] for d in cursor.description]
    usuarios = []
    for fila in cursor.fetchall():
        usuario = dict(zip(columnas, fila))
        usuario["enviados"] = set(usuario["enviados"] or [])
        usuarios.append(usuario)
    return usuarios


def _registrar(cursor, aviso, estado, detalle=None):
    cursor.execute(
        """
        INSERT INTO aviso_actualizacion
            (id_usuario, fecha_limite, umbral, estado, detalle)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id_usuario, fecha_limite, umbral) DO UPDATE
            SET estado = EXCLUDED.estado,
                detalle = EXCLUDED.detalle,
                fecha_envio = NOW()
        """,
        (aviso["id_usuario"], aviso["fecha_limite"], aviso["umbral"], estado, detalle),
    )


def enviar_recordatorios(simular=False, hoy=None, enviar=enviar_correo):
    """Envía los recordatorios del día. Devuelve un resumen.

    Con ``simular=True`` solo informa a quién se escribiría, sin enviar ni
    registrar nada.
    """
    resumen = {"candidatos": 0, "enviados": 0, "errores": 0, "detalle": []}
    config = None if simular else configuracion_smtp()
    if not simular and not config:
        resumen["detalle"].append(
            "Envío desactivado: falta configurar SMTP_HOST, SMTP_USUARIO y "
            "SMTP_PASSWORD."
        )
        return resumen

    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")

    url_app = obtener_variable("APP_URL")
    try:
        with conn.cursor() as cursor:
            avisos = planificar_avisos(_obtener_candidatos(cursor), hoy)
        resumen["candidatos"] = len(avisos)

        for aviso in avisos:
            asunto, cuerpo = redactar(aviso, url_app)
            etiqueta = (
                f"{aviso['nombre_completo']} <{aviso['correo_institucional']}> "
                f"(etapa {aviso['umbral']} días, vence {aviso['fecha_limite']:%d/%m/%Y})"
            )
            if simular:
                resumen["detalle"].append(f"[simulación] {etiqueta}")
                continue
            try:
                enviar(aviso["correo_institucional"], asunto, cuerpo, config=config)
            except CorreoError as e:
                estado, detalle = ESTADO_ERROR, str(e)[:500]
                resumen["errores"] += 1
                logger.warning("Recordatorio no enviado: %s", e)
            else:
                estado, detalle = ESTADO_ENVIADO, None
                resumen["enviados"] += 1
            # Cada envío se confirma por separado: un fallo no borra los demás.
            with conn:
                with conn.cursor() as cursor:
                    _registrar(cursor, aviso, estado, detalle)
            resumen["detalle"].append(f"[{estado.lower()}] {etiqueta}")
    finally:
        conn.close()

    logger.info(
        "Recordatorios: %s candidato(s), %s enviado(s), %s error(es)",
        resumen["candidatos"], resumen["enviados"], resumen["errores"],
    )
    return resumen


def ultimos_avisos(limite=50):
    """Últimos correos de recordatorio, para el panel de IT."""
    from src.core.database import get_engine

    import pandas as pd

    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    query = """
        SELECT a.fecha_envio, u.nombre_completo, u.correo_institucional,
               a.umbral AS etapa_dias, a.fecha_limite, a.estado, a.detalle
        FROM aviso_actualizacion a
        JOIN usuario u ON a.id_usuario = u.id_usuario
        ORDER BY a.fecha_envio DESC
        LIMIT %s
    """
    return pd.read_sql_query(query, engine, params=(limite,))
