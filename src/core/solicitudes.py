# Servicio transaccional del ciclo de vida de las solicitudes.
#
# Centraliza las escrituras en PostgreSQL para garantizar que:
#   1. El registro y su historial se guarden en la misma transacción (ACID).
#   2. Solo se permitan las transiciones definidas en workflow.py.
#   3. Cada cambio de estado quede auditado con usuario, fecha y observación.

import pandas as pd

from src.core.crypto import cifrar, descifrar_campos
from src.core.database import get_connection, get_engine
from src.core.feriados import fechas_feriados
from src.core.logging_config import obtener_logger
from src.core.utils import calcular_dias_habiles
from src.core.validaciones import (
    ValidacionError,
    validar_fechas,
    validar_saldo_vacaciones,
)
from src.core.vigencia import marcar_actividad
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
    puede_transicionar,
)

logger = obtener_logger("setesa.solicitudes")


class TransicionInvalida(Exception):
    """El cambio de estado no respeta el orden del workflow."""

    def __init__(self, estado_actual, estado_nuevo):
        self.estado_actual = estado_actual
        self.estado_nuevo = estado_nuevo
        super().__init__(
            f"Transición no permitida: '{estado_actual}' -> '{estado_nuevo}'."
        )


class SolicitudNoEncontrada(Exception):
    """No existe una solicitud con el identificador indicado."""


class FirmaRequerida(Exception):
    """La transición exige una firma electrónica que no fue enviada."""

    def __init__(self, estado_nuevo):
        self.estado_nuevo = estado_nuevo
        super().__init__(
            f"La transición a '{estado_nuevo}' requiere una firma electrónica."
        )


# Columna donde se persiste la firma según el estado al que se transiciona.
# Es una lista blanca: nunca se interpola texto del usuario en el SQL.
_COLUMNA_FIRMA = {
    ESTADO_PENDIENTE_APROBACION_GERENCIA: "firma_jefe_gtc",
    ESTADO_FINALIZADA: "firma_gerencia",
}


def _firma_valida(firma_b64):
    return bool(firma_b64 and isinstance(firma_b64, str) and firma_b64.strip())


def _registrar_historial(
    cursor, id_solicitud, estado_anterior, estado_nuevo, id_usuario, observacion=None
):
    cursor.execute(
        """
        INSERT INTO solicitud_historial
            (id_solicitud, estado_anterior, estado_nuevo, id_usuario, observacion)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (id_solicitud, estado_anterior, estado_nuevo, id_usuario, observacion),
    )


def registrar_solicitud(
    id_usuario,
    tipo_ausencia,
    fecha_inicio,
    fecha_fin,
    jefe_gtc,
    puesto,
    codigo_empleado,
    dias_solicitados,
    explicacion,
    firma_empleado_b64=None,
):
    """Registra una solicitud y la deja lista para la firma del Coordinador GTC.

    Implementa la decisión D-01 (opción C): la solicitud nace en 'Ingresada'
    y, dentro de la misma transacción, pasa a 'Pendiente de Firma Coordinador'.
    Ambos eventos quedan en solicitud_historial.

    Devuelve el id_solicitud generado. Lanza excepción si falla la transacción.
    """
    validar_fechas(fecha_inicio, fecha_fin)

    # H-17: los días se recalculan en el servidor descontando feriados.
    feriados = fechas_feriados(fecha_inicio, fecha_fin)
    dias_calculados = calcular_dias_habiles(fecha_inicio, fecha_fin, feriados)
    if dias_calculados <= 0:
        raise ValidacionError("El rango seleccionado no contiene días hábiles.")
    if dias_solicitados is None or dias_solicitados <= 0:
        dias_solicitados = dias_calculados
    elif int(dias_solicitados) != dias_calculados:
        raise ValidacionError(
            f"Los días solicitados ({dias_solicitados}) no coinciden con los "
            f"días hábiles del rango ({dias_calculados})."
        )

    # RF-01: no se puede solicitar más vacaciones de las disponibles.
    validar_saldo_vacaciones(
        id_usuario, tipo_ausencia, dias_calculados, fecha_inicio
    )

    # H-11: la explicación y la firma se guardan cifradas en reposo.
    explicacion_cifrada = cifrar(explicacion)
    firma_cifrada = cifrar(firma_empleado_b64)

    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")

    try:
        with conn:  # commit al salir; rollback si hay excepción
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO solicitud
                        (id_usuario, tipo_ausencia, fecha_inicio, fecha_fin,
                         estado_workflow, jefe_gtc, puesto, codigo_empleado,
                         dias_solicitados, explicacion, firma_empleado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_solicitud
                    """,
                    (
                        id_usuario,
                        tipo_ausencia,
                        fecha_inicio,
                        fecha_fin,
                        ESTADO_INGRESADA,
                        jefe_gtc,
                        puesto,
                        codigo_empleado,
                        dias_solicitados,
                        explicacion_cifrada,
                        firma_cifrada,
                    ),
                )
                id_solicitud = cursor.fetchone()[0]

                _registrar_historial(
                    cursor,
                    id_solicitud,
                    None,
                    ESTADO_INGRESADA,
                    id_usuario,
                    "Registro inicial de la solicitud.",
                )

                cursor.execute(
                    "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
                    (ESTADO_PENDIENTE_FIRMA_COORDINADOR, id_solicitud),
                )
                _registrar_historial(
                    cursor,
                    id_solicitud,
                    ESTADO_INGRESADA,
                    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
                    id_usuario,
                    "Enviada para firma del Coordinador GTC.",
                )

                # H-01: registrar actividad del usuario en la misma transacción.
                marcar_actividad(cursor, id_usuario)

        logger.info(
            "Solicitud %s registrada por usuario %s (%s, %s a %s)",
            id_solicitud,
            id_usuario,
            tipo_ausencia,
            fecha_inicio,
            fecha_fin,
        )
        return id_solicitud
    finally:
        conn.close()


def cambiar_estado(
    id_solicitud, estado_nuevo, id_usuario, observacion=None, firma_b64=None
):
    """Aplica una transición validada y la registra en el historial.

    Si la transición corresponde a una firma (Coordinador GTC o Gerencia),
    ``firma_b64`` es obligatoria y se persiste en la columna correspondiente
    dentro de la misma transacción.

    Devuelve una tupla (estado_anterior, estado_nuevo). Lanza
    TransicionInvalida si el salto no está permitido, SolicitudNoEncontrada
    si el id no existe y FirmaRequerida si falta la firma exigida.
    """
    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT estado_workflow FROM solicitud WHERE id_solicitud = %s FOR UPDATE",
                    (id_solicitud,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise SolicitudNoEncontrada(
                        f"No existe la solicitud con id {id_solicitud}."
                    )

                estado_anterior = fila[0]
                if not puede_transicionar(estado_anterior, estado_nuevo):
                    raise TransicionInvalida(estado_anterior, estado_nuevo)

                columna_firma = _COLUMNA_FIRMA.get(estado_nuevo)
                if columna_firma and not _firma_valida(firma_b64):
                    raise FirmaRequerida(estado_nuevo)

                if columna_firma:
                    firma_cifrada = cifrar(firma_b64)
                    cursor.execute(
                        f"""
                        UPDATE solicitud
                        SET estado_workflow = %s, {columna_firma} = %s
                        WHERE id_solicitud = %s AND estado_workflow = %s
                        """,
                        (estado_nuevo, firma_cifrada, id_solicitud, estado_anterior),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE solicitud
                        SET estado_workflow = %s
                        WHERE id_solicitud = %s AND estado_workflow = %s
                        """,
                        (estado_nuevo, id_solicitud, estado_anterior),
                    )
                if cursor.rowcount != 1:
                    raise TransicionInvalida(estado_anterior, estado_nuevo)

                _registrar_historial(
                    cursor,
                    id_solicitud,
                    estado_anterior,
                    estado_nuevo,
                    id_usuario,
                    observacion,
                )

                # H-01: firmar/aprobar también cuenta como actividad.
                marcar_actividad(cursor, id_usuario)

        logger.info(
            "Solicitud %s: %s -> %s (usuario %s)",
            id_solicitud,
            estado_anterior,
            estado_nuevo,
            id_usuario,
        )
        return estado_anterior, estado_nuevo
    finally:
        conn.close()


def obtener_solicitud(id_solicitud):
    """Devuelve la solicitud completa (con el nombre del colaborador) o None."""
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.*, u.nombre_completo
                FROM solicitud s
                JOIN usuario u ON s.id_usuario = u.id_usuario
                WHERE s.id_solicitud = %s
                """,
                (id_solicitud,),
            )
            fila = cursor.fetchone()
            if not fila:
                return None
            columnas = [descripcion[0] for descripcion in cursor.description]
            return descifrar_campos(dict(zip(columnas, fila)))
    finally:
        conn.close()


def actualizar_ruta_pdf(id_solicitud, ruta_pdf):
    """Guarda en la solicitud la ruta del último PDF oficial generado."""
    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE solicitud SET ruta_pdf = %s WHERE id_solicitud = %s",
                    (str(ruta_pdf), id_solicitud),
                )
                return cursor.rowcount == 1
    finally:
        conn.close()


def actualizar_hash_pdf(id_solicitud, pdf_hash):
    """Persiste el sello SHA-256 del PDF oficial (H-13)."""
    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE solicitud
                    SET pdf_hash = %s, pdf_hash_fecha = NOW()
                    WHERE id_solicitud = %s
                    """,
                    (pdf_hash, id_solicitud),
                )
                return cursor.rowcount == 1
    finally:
        conn.close()


def obtener_estado(id_solicitud):
    """Devuelve el estado actual de una solicitud, o None si no existe."""
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT estado_workflow FROM solicitud WHERE id_solicitud = %s",
                (id_solicitud,),
            )
            fila = cursor.fetchone()
            return fila[0] if fila else None
    finally:
        conn.close()


def obtener_historial(id_solicitud):
    """Devuelve el historial de estados de una solicitud como DataFrame."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    query = """
        SELECT h.fecha, h.estado_anterior, h.estado_nuevo,
               u.nombre_completo AS actor, h.observacion
        FROM solicitud_historial h
        LEFT JOIN usuario u ON h.id_usuario = u.id_usuario
        WHERE h.id_solicitud = %s
        ORDER BY h.fecha ASC, h.id_historial ASC
    """
    return pd.read_sql_query(query, engine, params=(id_solicitud,))
