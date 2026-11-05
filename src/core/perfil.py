# Fase 14: módulo "Mis datos" (tesis 1.5 y objetivo c).
#
# Consultor y Contabilidad confirman o actualizan sus datos al menos cada
# 6 meses; cada confirmación reinicia el plazo. Quien no lo hace pasa a baja
# lógica (ver src/core/vigencia.py y docs/triggers.sql).
#
#   - Consultor: puesto, código de empleado y teléfono de contacto.
#   - Contabilidad y RR.HH.: puesto y teléfono de contacto.
#
# Nombre, correo y rol los administra IT. El teléfono se guarda cifrado.

import datetime
import re

from dateutil.relativedelta import relativedelta

from src.core.cache import escritura, lectura
from src.core.crypto import cifrar, descifrar
from src.core.database import get_connection
from src.core.logging_config import obtener_logger
from src.core.vigencia import (
    DIAS_AVISO,
    MESES_VIGENCIA,
    ROLES_CON_ACTUALIZACION,
    marcar_actividad,
)

logger = obtener_logger("setesa.perfil")

ACCION_ACTUALIZACION = "ACTUALIZACION_DATOS"

CAMPOS_POR_ROL = {
    "Consultor": ("puesto", "codigo_empleado", "telefono"),
    "Contabilidad": ("puesto", "telefono"),
}

ETIQUETAS = {
    "puesto": "Puesto",
    "codigo_empleado": "Código de empleado",
    "telefono": "Teléfono de contacto",
}

_PATRON_TELEFONO = re.compile(r"^\+?\d{8,15}$")


class PerfilError(Exception):
    """Error controlado del módulo Mis datos."""


def requiere_actualizacion(nombre_rol):
    return nombre_rol in ROLES_CON_ACTUALIZACION


def fecha_limite(fecha_actualizacion):
    """Último día para actualizar los datos (6 meses después)."""
    if fecha_actualizacion is None:
        return None
    if isinstance(fecha_actualizacion, datetime.datetime):
        fecha_actualizacion = fecha_actualizacion.date()
    return fecha_actualizacion + relativedelta(months=MESES_VIGENCIA)


def dias_restantes(fecha_actualizacion, hoy=None):
    limite = fecha_limite(fecha_actualizacion)
    if limite is None:
        return None
    return (limite - (hoy or datetime.date.today())).days


def en_periodo_de_aviso(fecha_actualizacion, hoy=None):
    restantes = dias_restantes(fecha_actualizacion, hoy)
    return restantes is not None and restantes <= DIAS_AVISO


def normalizar_telefono(telefono):
    """Quita espacios, guiones y paréntesis; exige 8 a 15 dígitos."""
    valor = re.sub(r"[\s\-()]", "", telefono or "")
    if not _PATRON_TELEFONO.match(valor):
        raise PerfilError(
            "El teléfono debe tener entre 8 y 15 dígitos (puede iniciar con +)."
        )
    return valor


def _texto(valor, etiqueta, maximo):
    limpio = (valor or "").strip()
    if not limpio:
        raise PerfilError(f"{etiqueta} es obligatorio.")
    if len(limpio) > maximo:
        raise PerfilError(f"{etiqueta} admite como máximo {maximo} caracteres.")
    return limpio


def validar_datos(nombre_rol, puesto, codigo_empleado, telefono):
    """Devuelve solo los campos que el rol actualiza, ya validados."""
    if not requiere_actualizacion(nombre_rol):
        raise PerfilError(
            f"El rol {nombre_rol} no actualiza sus datos en este módulo."
        )
    datos = {
        "puesto": _texto(puesto, "El puesto", 150),
        "telefono": normalizar_telefono(telefono),
    }
    if "codigo_empleado" in CAMPOS_POR_ROL[nombre_rol]:
        datos["codigo_empleado"] = _texto(
            codigo_empleado, "El código de empleado", 50
        )
    return datos


@lectura(ttl=60)
def obtener_perfil(id_usuario):
    """Datos del usuario con su plazo de actualización, o None."""
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.nombre_completo, u.correo_institucional, r.nombre_rol,
                       u.puesto, u.codigo_empleado, u.telefono,
                       u.fecha_actualizacion_datos
                FROM usuario u
                JOIN rol r ON u.id_rol = r.id_rol
                WHERE u.id_usuario = %s
                """,
                (id_usuario,),
            )
            fila = cursor.fetchone()
    finally:
        conn.close()
    if not fila:
        return None

    nombre, correo, rol, puesto, codigo, telefono, actualizado = fila
    perfil = {
        "nombre_completo": nombre,
        "correo_institucional": correo,
        "nombre_rol": rol,
        "puesto": puesto or "",
        "codigo_empleado": codigo or "",
        "telefono": descifrar(telefono) or "",
        "fecha_actualizacion_datos": actualizado,
        "requiere_actualizacion": requiere_actualizacion(rol),
        "fecha_limite": None,
        "dias_restantes": None,
    }
    if perfil["requiere_actualizacion"]:
        perfil["fecha_limite"] = fecha_limite(actualizado)
        perfil["dias_restantes"] = dias_restantes(actualizado)
    return perfil


@escritura
def actualizar_mis_datos(id_usuario, puesto, codigo_empleado=None, telefono=None):
    """Guarda los datos, reinicia el plazo de 6 meses y lo audita.

    Devuelve la nueva fecha límite. Lanza PerfilError si algo no procede.
    """
    conn = get_connection()
    if not conn:
        raise PerfilError("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.nombre_rol, u.estado_vigencia,
                           u.puesto, u.codigo_empleado, u.telefono
                    FROM usuario u
                    JOIN rol r ON u.id_rol = r.id_rol
                    WHERE u.id_usuario = %s
                    FOR UPDATE OF u
                    """,
                    (id_usuario,),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise PerfilError(f"No existe el usuario con id {id_usuario}.")
                rol, vigente, puesto_ant, codigo_ant, telefono_ant = fila
                if not vigente:
                    raise PerfilError("Su cuenta no está vigente. Contacte a IT.")

                datos = validar_datos(rol, puesto, codigo_empleado, telefono)
                anteriores = {
                    "puesto": puesto_ant or "",
                    "codigo_empleado": codigo_ant or "",
                    "telefono": descifrar(telefono_ant) or "",
                }
                cambiados = [
                    ETIQUETAS[campo]
                    for campo, valor in datos.items()
                    if valor != anteriores[campo]
                ]

                asignaciones = ", ".join(f"{campo} = %s" for campo in datos)
                valores = [
                    cifrar(valor) if campo == "telefono" else valor
                    for campo, valor in datos.items()
                ]
                cursor.execute(
                    f"""
                    UPDATE usuario
                    SET {asignaciones}, fecha_actualizacion_datos = NOW()
                    WHERE id_usuario = %s
                    RETURNING estado_vigencia, fecha_actualizacion_datos
                    """,
                    (*valores, id_usuario),
                )
                vigente, actualizado = cursor.fetchone()
                vencido = not vigente
                # Si el plazo ya había vencido, el trigger aplicó la baja
                # lógica: se confirma la transacción y se avisa después.
                if not vencido:
                    # Auditoría sin valores: el teléfono es un dato personal.
                    cursor.execute(
                        """
                        INSERT INTO usuario_log
                            (id_ejecutor, id_afectado, accion, detalle)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            id_usuario,
                            id_usuario,
                            ACCION_ACTUALIZACION,
                            "Cambios: "
                            + (", ".join(cambiados) or "ninguno (confirmación)"),
                        ),
                    )
                    marcar_actividad(cursor, id_usuario)
    finally:
        conn.close()

    if vencido:
        raise PerfilError(
            "El plazo de 6 meses para actualizar sus datos ya venció y su "
            "cuenta pasó a baja lógica. Contacte a IT."
        )

    logger.info("Usuario %s actualizó sus datos", id_usuario)
    return fecha_limite(actualizado)
