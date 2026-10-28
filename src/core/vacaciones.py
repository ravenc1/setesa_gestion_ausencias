# Saldo de vacaciones del consultor (RF-01 / decisión D-03).
#
# Saldo = días asignados en `usuario.dias_vacaciones_asignados` menos los días
# solicitados como VACACION en el año de referencia. Se calcula contra la base
# para que el panel y la validación del servidor usen la misma fuente.

import datetime

from src.core.database import get_connection

DIAS_VACACIONES_DEFAULT = 15
TIPO_VACACION = "VACACION"


def obtener_saldo_vacaciones(id_usuario, anio=None, fecha_referencia=None):
    """Devuelve asignados, usados y disponibles del usuario en el año.

    `fecha_referencia` permite calcular el saldo del año de la solicitud;
    si no se indica, se usa el año en curso.
    """
    if anio is None:
        referencia = fecha_referencia or datetime.date.today()
        anio = referencia.year

    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT dias_vacaciones_asignados
                FROM usuario
                WHERE id_usuario = %s
                """,
                (id_usuario,),
            )
            fila = cursor.fetchone()
            if not fila:
                raise ValueError(f"No existe el usuario con id {id_usuario}.")

            asignados = fila[0]
            if asignados is None:
                asignados = DIAS_VACACIONES_DEFAULT

            cursor.execute(
                """
                SELECT COALESCE(SUM(dias_solicitados), 0)
                FROM solicitud
                WHERE id_usuario = %s
                  AND tipo_ausencia = %s
                  AND EXTRACT(YEAR FROM fecha_inicio) = %s
                """,
                (id_usuario, TIPO_VACACION, int(anio)),
            )
            usados = int(cursor.fetchone()[0] or 0)
    finally:
        conn.close()

    return {
        "anio": int(anio),
        "asignados": int(asignados),
        "usados": usados,
        "disponibles": int(asignados) - usados,
    }
