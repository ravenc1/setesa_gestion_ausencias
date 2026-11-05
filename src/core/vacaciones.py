# Saldo de vacaciones del consultor (RF-01 / decisión D-03).
#
# Saldo = días asignados en `usuario.dias_vacaciones_asignados` menos los días
# solicitados como VACACION en el año de referencia. Se calcula contra la base
# para que el panel y la validación del servidor usen la misma fuente.

import datetime

from src.core.cache import lectura
from src.core.database import get_connection

DIAS_VACACIONES_DEFAULT = 15
TIPO_VACACION = "VACACION"


def calcular_saldo_vacaciones(id_usuario, anio=None, fecha_referencia=None):
    """Calcula asignados, usados y disponibles del usuario directo de la base.

    `fecha_referencia` permite calcular el saldo del año de la solicitud;
    si no se indica, se usa el año en curso. Es la lectura que usan las
    validaciones de negocio: nunca viene de una copia temporal.
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
                  -- Fase 16: los días denegados vuelven al saldo.
                  AND resolucion IS DISTINCT FROM 'Retirada'
                  AND resolucion IS DISTINCT FROM 'Denegada'
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


@lectura(ttl=20)
def obtener_saldo_vacaciones(id_usuario, anio=None, fecha_referencia=None):
    """Igual que ``calcular_saldo_vacaciones``, con copia temporal para la pantalla."""
    return calcular_saldo_vacaciones(id_usuario, anio, fecha_referencia)
