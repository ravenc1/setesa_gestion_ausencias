# Servicio de feriados nacionales (RF-01 / decisión D-04).
#
# Los feriados viven en la tabla `feriado` para que Gerencia pueda mantenerlos
# sin tocar código. `calcular_dias_habiles` recibe el conjunto de fechas y las
# excluye del conteo.

import datetime

import pandas as pd

from src.core.database import get_connection


class FeriadoError(Exception):
    """Operación inválida sobre el catálogo de feriados."""


def _a_fecha(valor):
    if isinstance(valor, datetime.datetime):
        return valor.date()
    return valor


def fechas_feriados(desde, hasta):
    """Devuelve el conjunto de fechas feriadas en el rango (inclusive)."""
    desde = _a_fecha(desde)
    hasta = _a_fecha(hasta)
    if desde is None or hasta is None or hasta < desde:
        return set()

    conn = get_connection()
    if not conn:
        return set()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT fecha FROM feriado WHERE fecha BETWEEN %s AND %s",
                (desde, hasta),
            )
            return {_a_fecha(fila[0]) for fila in cursor.fetchall()}
    finally:
        conn.close()


def listar_feriados(anio=None):
    """Devuelve el catálogo ordenado por fecha (opcionalmente por año)."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame(columns=["id_feriado", "fecha", "nombre"])

    try:
        query = "SELECT id_feriado, fecha, nombre FROM feriado"
        params = None
        if anio is not None:
            query += " WHERE EXTRACT(YEAR FROM fecha) = %s"
            params = (int(anio),)
        query += " ORDER BY fecha"
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def crear_feriado(fecha, nombre):
    """Crea o actualiza el feriado de una fecha. Devuelve su id."""
    fecha = _a_fecha(fecha)
    nombre = (nombre or "").strip()
    if fecha is None:
        raise FeriadoError("La fecha del feriado es obligatoria.")
    if not nombre:
        raise FeriadoError("El nombre del feriado es obligatorio.")

    conn = get_connection()
    if not conn:
        raise FeriadoError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO feriado (fecha, nombre)
                    VALUES (%s, %s)
                    ON CONFLICT (fecha)
                    DO UPDATE SET nombre = EXCLUDED.nombre
                    RETURNING id_feriado
                    """,
                    (fecha, nombre),
                )
                return cursor.fetchone()[0]
    finally:
        conn.close()


def eliminar_feriado(id_feriado):
    """Elimina un feriado del catálogo. Devuelve True si existía."""
    conn = get_connection()
    if not conn:
        raise FeriadoError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM feriado WHERE id_feriado = %s",
                    (id_feriado,),
                )
                return cursor.rowcount > 0
    finally:
        conn.close()
