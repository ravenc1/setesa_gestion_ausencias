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
from src.core.recordatorios import marcar_atendidos
from src.core.utils import calcular_dias_habiles
from src.core.validaciones import (
    ValidacionError,
    validar_fechas,
    validar_saldo_vacaciones,
)
from src.core.vigencia import marcar_actividad
from src.core.workflow import (
    ETAPAS_DENEGACION,
    RESOLUCION_APROBADA,
    RESOLUCION_DENEGADA,
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


class CoordinadorNoAsignado(Exception):
    """Quien intenta firmar no es el Coordinador GTC asignado al expediente."""

    def __init__(self, id_solicitud):
        self.id_solicitud = id_solicitud
        super().__init__(
            f"El expediente {id_solicitud} está asignado a otro Coordinador GTC; "
            "solo el coordinador asignado puede darle su visto bueno."
        )


class MotivoRequerido(Exception):
    """La denegación exige un motivo."""


class NoAutorizadoParaDenegar(Exception):
    """El usuario no puede denegar el expediente en su etapa actual."""


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


def _coordinador_vigente(cursor, id_coordinador):
    """Nombre del Coordinador GTC vigente con ese id, o None."""
    cursor.execute(
        """
        SELECT u.nombre_completo
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.id_usuario = %s
          AND r.nombre_rol = 'Coordinador GTC'
          AND u.estado_vigencia = TRUE
        """,
        (id_coordinador,),
    )
    fila = cursor.fetchone()
    return fila[0] if fila else None


def registrar_solicitud(
    id_usuario,
    tipo_ausencia,
    fecha_inicio,
    fecha_fin,
    id_coordinador,
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

    ``id_coordinador`` es el usuario Coordinador GTC (jefe inmediato) que
    recibirá el expediente en su bandeja. Debe estar vigente; su nombre se
    copia en ``jefe_gtc`` para el PDF oficial.

    Devuelve el id_solicitud generado. Lanza excepción si falla la transacción.
    """
    validar_fechas(fecha_inicio, fecha_fin)
    if not id_coordinador:
        raise ValidacionError("Debe seleccionar al Jefe Inmediato GTC.")

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
                jefe_gtc = _coordinador_vigente(cursor, id_coordinador)
                if not jefe_gtc:
                    raise ValidacionError(
                        "El Jefe Inmediato GTC seleccionado no es un "
                        "Coordinador GTC vigente."
                    )

                cursor.execute(
                    """
                    INSERT INTO solicitud
                        (id_usuario, tipo_ausencia, fecha_inicio, fecha_fin,
                         estado_workflow, jefe_gtc, id_coordinador, puesto,
                         codigo_empleado, dias_solicitados, explicacion,
                         firma_empleado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_solicitud
                    """,
                    (
                        id_usuario,
                        tipo_ausencia,
                        fecha_inicio,
                        fecha_fin,
                        ESTADO_INGRESADA,
                        jefe_gtc,
                        id_coordinador,
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
    si el id no existe, FirmaRequerida si falta la firma exigida y
    CoordinadorNoAsignado si firma un Coordinador GTC distinto al asignado.
    """
    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT estado_workflow, id_coordinador
                    FROM solicitud
                    WHERE id_solicitud = %s
                    FOR UPDATE
                    """,
                    (id_solicitud,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise SolicitudNoEncontrada(
                        f"No existe la solicitud con id {id_solicitud}."
                    )

                estado_anterior, id_coordinador = fila
                if not puede_transicionar(estado_anterior, estado_nuevo):
                    raise TransicionInvalida(estado_anterior, estado_nuevo)

                # Solo el coordinador asignado da el visto bueno del banco.
                if (
                    estado_nuevo == ESTADO_PENDIENTE_APROBACION_GERENCIA
                    and id_coordinador != id_usuario
                ):
                    raise CoordinadorNoAsignado(id_solicitud)

                columna_firma = _COLUMNA_FIRMA.get(estado_nuevo)
                if columna_firma and not _firma_valida(firma_b64):
                    raise FirmaRequerida(estado_nuevo)

                if columna_firma:
                    firma_cifrada = cifrar(firma_b64)
                    # Fase 16: la aprobación de Gerencia deja la resolución.
                    finaliza = estado_nuevo == ESTADO_FINALIZADA
                    resolucion = (
                        ", resolucion = %s, fecha_resolucion = NOW(), "
                        "id_resuelve = %s"
                        if finaliza
                        else ""
                    )
                    extra = (RESOLUCION_APROBADA, id_usuario) if finaliza else ()
                    cursor.execute(
                        f"""
                        UPDATE solicitud
                        SET estado_workflow = %s, {columna_firma} = %s{resolucion}
                        WHERE id_solicitud = %s AND estado_workflow = %s
                        """,
                        (
                            estado_nuevo,
                            firma_cifrada,
                            *extra,
                            id_solicitud,
                            estado_anterior,
                        ),
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

                # R-11: la firma del banco atiende los recordatorios pendientes
                # del expediente dentro de la misma transacción.
                if estado_nuevo == ESTADO_PENDIENTE_APROBACION_GERENCIA:
                    marcar_atendidos(cursor, id_solicitud)

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


# Columna de la firma de quien deniega, según la etapa.
_FIRMA_DENEGACION = {
    ESTADO_PENDIENTE_FIRMA_COORDINADOR: "firma_jefe_gtc",
    ESTADO_PENDIENTE_APROBACION_GERENCIA: "firma_gerencia",
}

_TEXTO_DENEGACION = {
    ESTADO_PENDIENTE_FIRMA_COORDINADOR: "Solicitud denegada por el Coordinador GTC.",
    ESTADO_PENDIENTE_APROBACION_GERENCIA: "Solicitud denegada por Gerencia.",
}

MOTIVO_MIN = 10


def denegar_solicitud(id_solicitud, id_usuario, motivo, firma_b64):
    """Deniega el expediente y cierra el flujo (Fase 16).

    - En 'Pendiente de Firma Coordinador' deniega el Coordinador GTC asignado
      (el banco no otorga el permiso).
    - En 'Pendiente de Aprobación Gerencia' deniega Gerencia.

    El motivo es obligatorio y se guarda cifrado; la firma de quien deniega
    queda en el expediente. Los días de vacaciones vuelven al saldo porque el
    saldo no cuenta solicitudes denegadas. Devuelve el estado anterior.
    """
    texto = (motivo or "").strip()
    if len(texto) < MOTIVO_MIN:
        raise MotivoRequerido(
            f"Indique el motivo de la denegación (mínimo {MOTIVO_MIN} caracteres)."
        )
    if not _firma_valida(firma_b64):
        raise FirmaRequerida(ESTADO_FINALIZADA)

    conn = get_connection()
    if not conn:
        raise RuntimeError("No hay conexión a la base de datos.")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.estado_workflow, s.id_coordinador, r.nombre_rol
                    FROM solicitud s
                    JOIN usuario u ON u.id_usuario = %s
                    JOIN rol r ON r.id_rol = u.id_rol
                    WHERE s.id_solicitud = %s
                    FOR UPDATE OF s
                    """,
                    (id_usuario, id_solicitud),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise SolicitudNoEncontrada(
                        f"No existe la solicitud con id {id_solicitud}."
                    )
                estado_anterior, id_coordinador, rol = fila

                if estado_anterior not in ETAPAS_DENEGACION:
                    raise TransicionInvalida(estado_anterior, ESTADO_FINALIZADA)
                if estado_anterior == ESTADO_PENDIENTE_FIRMA_COORDINADOR:
                    if id_coordinador != id_usuario:
                        raise CoordinadorNoAsignado(id_solicitud)
                elif rol != ETAPAS_DENEGACION[estado_anterior]:
                    raise NoAutorizadoParaDenegar(
                        "Solo Gerencia puede denegar un expediente que espera "
                        "su aprobación."
                    )

                columna_firma = _FIRMA_DENEGACION[estado_anterior]
                cursor.execute(
                    f"""
                    UPDATE solicitud
                    SET estado_workflow = %s,
                        {columna_firma} = %s,
                        resolucion = %s,
                        motivo_resolucion = %s,
                        fecha_resolucion = NOW(),
                        id_resuelve = %s
                    WHERE id_solicitud = %s AND estado_workflow = %s
                    """,
                    (
                        ESTADO_FINALIZADA,
                        cifrar(firma_b64),
                        RESOLUCION_DENEGADA,
                        cifrar(texto),
                        id_usuario,
                        id_solicitud,
                        estado_anterior,
                    ),
                )
                if cursor.rowcount != 1:
                    raise TransicionInvalida(estado_anterior, ESTADO_FINALIZADA)

                # El motivo no va al historial: puede ser sensible y allí no
                # se cifra. Queda cifrado en solicitud.motivo_resolucion.
                _registrar_historial(
                    cursor,
                    id_solicitud,
                    estado_anterior,
                    ESTADO_FINALIZADA,
                    id_usuario,
                    _TEXTO_DENEGACION[estado_anterior],
                )
                if estado_anterior == ESTADO_PENDIENTE_FIRMA_COORDINADOR:
                    marcar_atendidos(cursor, id_solicitud)
                marcar_actividad(cursor, id_usuario)

        logger.info(
            "Solicitud %s denegada desde '%s' por usuario %s",
            id_solicitud,
            estado_anterior,
            id_usuario,
        )
        return estado_anterior
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
