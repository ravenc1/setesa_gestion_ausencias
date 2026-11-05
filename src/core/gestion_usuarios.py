# Gestión de usuarios desde el panel de IT (Fase 9).
#
# Reglas:
#   1. Solo el rol IT puede crear, editar, dar de baja, reactivar o resetear
#      contraseñas. La autorización se revalida contra la base, no solo contra
#      la sesión de Streamlit.
#   2. El correo registrado es el identificador de acceso (cualquier dominio
#      válido) y se normaliza a minúsculas.
#   3. La contraseña exige mínimo 8 caracteres, al menos una letra y un número.
#   4. Nadie puede desactivarse a sí mismo ni cambiarse el rol; tampoco se puede
#      dejar el sistema sin Administrador ni sin IT activo.
#   5. Cada operación se audita en `usuario_log` dentro de la misma transacción.
#
# Este módulo no importa Streamlit: puede usarse desde la UI y desde scripts.

import re

import pandas as pd

from src.core.database import get_connection, get_engine
from src.core.logging_config import obtener_logger
from src.core.security import ROL_IT, hash_password
from src.core.vigencia import ROLES_PROTEGIDOS

logger = obtener_logger("setesa.gestion_usuarios")

ACCION_CREACION = "CREACION"
ACCION_EDICION = "EDICION"
ACCION_BAJA = "BAJA"
ACCION_REACTIVACION = "REACTIVACION"
ACCION_RESET_PASSWORD = "RESET_PASSWORD"

DIAS_VACACIONES_MAX = 365
PASSWORD_MIN = 8

_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class GestionUsuariosError(Exception):
    """Error controlado de la gestión de usuarios."""


class DatosInvalidos(GestionUsuariosError):
    """Un dato no cumple el formato o la política definida."""


class CorreoDuplicado(GestionUsuariosError):
    """Ya existe una cuenta con ese correo registrado."""


class OperacionNoPermitida(GestionUsuariosError):
    """La operación rompe una regla de seguridad o de protección."""


def normalizar_correo(correo):
    """Valida el formato y devuelve el correo en minúsculas y sin espacios."""
    valor = (correo or "").strip().lower()
    if not valor:
        raise DatosInvalidos("El correo registrado es obligatorio.")
    if len(valor) > 150:
        raise DatosInvalidos("El correo registrado no puede superar 150 caracteres.")
    if not _PATRON_CORREO.match(valor):
        raise DatosInvalidos(
            "El correo registrado no tiene un formato válido "
            "(ejemplo: nombre@dominio.com)."
        )
    return valor


def validar_password(password):
    """Aplica la política: mínimo 8, al menos una letra y un número."""
    valor = password or ""
    if len(valor) < PASSWORD_MIN:
        raise DatosInvalidos(
            f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
        )
    if not any(c.isalpha() for c in valor):
        raise DatosInvalidos("La contraseña debe incluir al menos una letra.")
    if not any(c.isdigit() for c in valor):
        raise DatosInvalidos("La contraseña debe incluir al menos un número.")
    return valor


def _validar_nombre(nombre):
    valor = (nombre or "").strip()
    if len(valor) < 3:
        raise DatosInvalidos("El nombre completo debe tener al menos 3 caracteres.")
    if len(valor) > 150:
        raise DatosInvalidos("El nombre completo no puede superar 150 caracteres.")
    return valor


def _validar_dias(dias):
    try:
        valor = int(dias)
    except (TypeError, ValueError):
        raise DatosInvalidos("Los días de vacaciones deben ser un número entero.")
    if valor < 0 or valor > DIAS_VACACIONES_MAX:
        raise DatosInvalidos(
            f"Los días de vacaciones deben estar entre 0 y {DIAS_VACACIONES_MAX}."
        )
    return valor


def _validar_ejecutor(cursor, id_ejecutor):
    cursor.execute(
        """
        SELECT r.nombre_rol
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.id_usuario = %s AND u.estado_vigencia = TRUE
        """,
        (id_ejecutor,),
    )
    fila = cursor.fetchone()
    if not fila or fila[0] != ROL_IT:
        raise OperacionNoPermitida(
            "Solo el rol IT puede gestionar usuarios."
        )


def _resolver_rol(cursor, nombre_rol):
    cursor.execute("SELECT id_rol FROM rol WHERE nombre_rol = %s", (nombre_rol,))
    fila = cursor.fetchone()
    if not fila:
        raise DatosInvalidos(f"El rol '{nombre_rol}' no existe.")
    return fila[0]


def _contar_activos_rol(cursor, nombre_rol, excluir=None):
    query = """
        SELECT COUNT(*)
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE r.nombre_rol = %s AND u.estado_vigencia = TRUE
    """
    params = [nombre_rol]
    if excluir is not None:
        query += " AND u.id_usuario <> %s"
        params.append(excluir)
    cursor.execute(query, tuple(params))
    return cursor.fetchone()[0]


def _auditar(cursor, id_ejecutor, id_afectado, accion, detalle=None):
    cursor.execute(
        """
        INSERT INTO usuario_log
            (id_ejecutor, id_afectado, accion, detalle)
        VALUES (%s, %s, %s, %s)
        """,
        (id_ejecutor, id_afectado, accion, detalle),
    )


def listar_roles():
    """Roles disponibles para asignar."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame(columns=["id_rol", "nombre_rol"])
    return pd.read_sql_query(
        "SELECT id_rol, nombre_rol FROM rol ORDER BY id_rol", engine
    )


def listar_usuarios():
    """Usuarios con su rol, vigencia, actividad y saldo de vacaciones del año."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    query = """
        SELECT u.id_usuario,
               u.nombre_completo,
               u.correo_institucional,
               r.nombre_rol,
               COALESCE(u.estado_vigencia, TRUE) AS estado_vigencia,
               u.ultima_actividad,
               CASE WHEN r.nombre_rol IN ('Consultor', 'Contabilidad')
                    THEN (u.fecha_actualizacion_datos
                          + INTERVAL '6 months')::date
               END AS fecha_limite_datos,
               u.dias_vacaciones_asignados,
               COALESCE(v.dias_usados, 0) AS dias_usados,
               u.dias_vacaciones_asignados - COALESCE(v.dias_usados, 0)
                   AS dias_disponibles
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        LEFT JOIN (
            SELECT id_usuario, SUM(COALESCE(dias_solicitados, 0)) AS dias_usados
            FROM solicitud
            WHERE tipo_ausencia = 'VACACION'
              AND resolucion IS DISTINCT FROM 'Denegada'
              AND EXTRACT(YEAR FROM fecha_inicio)
                  = EXTRACT(YEAR FROM CURRENT_DATE)
            GROUP BY id_usuario
        ) v ON v.id_usuario = u.id_usuario
        ORDER BY COALESCE(u.estado_vigencia, TRUE) DESC,
                 r.nombre_rol ASC,
                 u.nombre_completo ASC
    """
    return pd.read_sql_query(query, engine)


def crear_usuario(
    id_ejecutor,
    nombre_completo,
    correo,
    nombre_rol,
    password,
    dias_vacaciones=15,
):
    """Crea una cuenta y registra la acción en `usuario_log`."""
    nombre = _validar_nombre(nombre_completo)
    correo_normalizado = normalizar_correo(correo)
    clave = validar_password(password)
    dias = _validar_dias(dias_vacaciones)

    conn = get_connection()
    if not conn:
        raise GestionUsuariosError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                _validar_ejecutor(cursor, id_ejecutor)
                id_rol = _resolver_rol(cursor, nombre_rol)

                cursor.execute(
                    """
                    SELECT 1 FROM usuario
                    WHERE LOWER(correo_institucional) = %s
                    """,
                    (correo_normalizado,),
                )
                if cursor.fetchone():
                    raise CorreoDuplicado(
                        f"Ya existe una cuenta con el correo {correo_normalizado}."
                    )

                cursor.execute(
                    """
                    INSERT INTO usuario
                        (id_rol, nombre_completo, correo_institucional,
                         password_hash, estado_vigencia, ultima_actividad,
                         dias_vacaciones_asignados)
                    VALUES (%s, %s, %s, %s, TRUE, NOW(), %s)
                    RETURNING id_usuario
                    """,
                    (
                        id_rol,
                        nombre,
                        correo_normalizado,
                        hash_password(clave),
                        dias,
                    ),
                )
                id_usuario = cursor.fetchone()[0]
                _auditar(
                    cursor,
                    id_ejecutor,
                    id_usuario,
                    ACCION_CREACION,
                    f"Rol={nombre_rol}; correo={correo_normalizado}; "
                    f"dias_vacaciones={dias}",
                )
        logger.info(
            "Usuario %s creado por %s (rol %s)",
            id_usuario,
            id_ejecutor,
            nombre_rol,
        )
        return id_usuario
    finally:
        conn.close()


def editar_usuario(
    id_ejecutor,
    id_usuario,
    nombre_completo,
    correo,
    nombre_rol,
    dias_vacaciones,
):
    """Actualiza nombre, correo, rol y días de vacaciones."""
    nombre = _validar_nombre(nombre_completo)
    correo_normalizado = normalizar_correo(correo)
    dias = _validar_dias(dias_vacaciones)

    conn = get_connection()
    if not conn:
        raise GestionUsuariosError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                _validar_ejecutor(cursor, id_ejecutor)
                id_rol_nuevo = _resolver_rol(cursor, nombre_rol)

                cursor.execute(
                    """
                    SELECT u.id_rol, r.nombre_rol, COALESCE(u.estado_vigencia, TRUE)
                    FROM usuario u
                    JOIN rol r ON u.id_rol = r.id_rol
                    WHERE u.id_usuario = %s
                    FOR UPDATE
                    """,
                    (id_usuario,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise GestionUsuariosError(
                        f"No existe el usuario con id {id_usuario}."
                    )
                _id_rol_actual, rol_actual, activo = fila

                if id_ejecutor == id_usuario and nombre_rol != rol_actual:
                    raise OperacionNoPermitida(
                        "No puede cambiar su propio rol."
                    )

                if (
                    activo
                    and rol_actual in ROLES_PROTEGIDOS
                    and nombre_rol != rol_actual
                    and _contar_activos_rol(cursor, rol_actual, excluir=id_usuario)
                    == 0
                ):
                    raise OperacionNoPermitida(
                        f"No se puede cambiar el rol del único usuario activo "
                        f"con rol {rol_actual}."
                    )

                cursor.execute(
                    """
                    SELECT 1 FROM usuario
                    WHERE LOWER(correo_institucional) = %s
                      AND id_usuario <> %s
                    """,
                    (correo_normalizado, id_usuario),
                )
                if cursor.fetchone():
                    raise CorreoDuplicado(
                        f"Ya existe otra cuenta con el correo {correo_normalizado}."
                    )

                cursor.execute(
                    """
                    UPDATE usuario
                       SET nombre_completo = %s,
                           correo_institucional = %s,
                           id_rol = %s,
                           dias_vacaciones_asignados = %s
                     WHERE id_usuario = %s
                    """,
                    (
                        nombre,
                        correo_normalizado,
                        id_rol_nuevo,
                        dias,
                        id_usuario,
                    ),
                )
                _auditar(
                    cursor,
                    id_ejecutor,
                    id_usuario,
                    ACCION_EDICION,
                    f"Rol={nombre_rol}; correo={correo_normalizado}; "
                    f"dias_vacaciones={dias}",
                )
        logger.info("Usuario %s editado por %s", id_usuario, id_ejecutor)
    finally:
        conn.close()


def cambiar_estado_usuario(id_ejecutor, id_usuario, activo):
    """Aplica baja lógica o reactivación, con protecciones y auditoría."""
    conn = get_connection()
    if not conn:
        raise GestionUsuariosError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                _validar_ejecutor(cursor, id_ejecutor)

                cursor.execute(
                    """
                    SELECT r.nombre_rol, COALESCE(u.estado_vigencia, TRUE)
                    FROM usuario u
                    JOIN rol r ON u.id_rol = r.id_rol
                    WHERE u.id_usuario = %s
                    FOR UPDATE
                    """,
                    (id_usuario,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise GestionUsuariosError(
                        f"No existe el usuario con id {id_usuario}."
                    )
                rol_actual, estado_actual = fila

                if activo:
                    if estado_actual:
                        return
                    cursor.execute(
                        """
                        UPDATE usuario
                           SET estado_vigencia = TRUE,
                               ultima_actividad = NOW(),
                               fecha_actualizacion_datos = NOW()
                         WHERE id_usuario = %s
                        """,
                        (id_usuario,),
                    )
                    _auditar(
                        cursor,
                        id_ejecutor,
                        id_usuario,
                        ACCION_REACTIVACION,
                        f"Rol={rol_actual}",
                    )
                    logger.info(
                        "Usuario %s reactivado por %s", id_usuario, id_ejecutor
                    )
                    return

                if not estado_actual:
                    return
                if id_ejecutor == id_usuario:
                    raise OperacionNoPermitida(
                        "No puede desactivar su propia cuenta."
                    )
                if (
                    rol_actual in ROLES_PROTEGIDOS
                    and _contar_activos_rol(cursor, rol_actual, excluir=id_usuario)
                    == 0
                ):
                    raise OperacionNoPermitida(
                        f"No se puede desactivar al único usuario activo "
                        f"con rol {rol_actual}."
                    )

                cursor.execute(
                    "UPDATE usuario SET estado_vigencia = FALSE WHERE id_usuario = %s",
                    (id_usuario,),
                )
                _auditar(
                    cursor,
                    id_ejecutor,
                    id_usuario,
                    ACCION_BAJA,
                    f"Rol={rol_actual}",
                )
        logger.info("Usuario %s dado de baja por %s", id_usuario, id_ejecutor)
    finally:
        conn.close()


def resetear_password(id_ejecutor, id_usuario, password):
    """Define una contraseña nueva con la política vigente."""
    clave = validar_password(password)

    conn = get_connection()
    if not conn:
        raise GestionUsuariosError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                _validar_ejecutor(cursor, id_ejecutor)
                cursor.execute(
                    "SELECT 1 FROM usuario WHERE id_usuario = %s FOR UPDATE",
                    (id_usuario,),
                )
                if not cursor.fetchone():
                    raise GestionUsuariosError(
                        f"No existe el usuario con id {id_usuario}."
                    )

                cursor.execute(
                    "UPDATE usuario SET password_hash = %s WHERE id_usuario = %s",
                    (hash_password(clave), id_usuario),
                )
                _auditar(
                    cursor,
                    id_ejecutor,
                    id_usuario,
                    ACCION_RESET_PASSWORD,
                    "Contraseña restablecida por IT",
                )
        logger.info(
            "Contraseña del usuario %s restablecida por %s",
            id_usuario,
            id_ejecutor,
        )
    finally:
        conn.close()


def listar_auditoria(limite=200):
    """Últimas acciones de gestión, con nombres de ejecutor y afectado."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    query = """
        SELECT l.id_log,
               l.fecha,
               COALESCE(e.nombre_completo, '(eliminado)') AS ejecutor,
               COALESCE(a.nombre_completo, '(eliminado)') AS afectado,
               l.accion,
               l.detalle
        FROM usuario_log l
        LEFT JOIN usuario e ON l.id_ejecutor = e.id_usuario
        LEFT JOIN usuario a ON l.id_afectado = a.id_usuario
        ORDER BY l.fecha DESC, l.id_log DESC
        LIMIT %s
    """
    return pd.read_sql_query(query, engine, params=(int(limite),))
