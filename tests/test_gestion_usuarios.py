# Fase 9: pruebas de la gestión de usuarios (rol IT).
#
# Cada prueba crea su propio ejecutor IT y sus usuarios temporales, y los
# elimina al finalizar. Las filas de `usuario_log` también se limpian para no
# dejar residuos en la base.

import os
from uuid import uuid4

import pytest

from src.core.database import get_connection
from src.core.gestion_usuarios import (
    CorreoDuplicado,
    DatosInvalidos,
    OperacionNoPermitida,
    cambiar_estado_usuario,
    crear_usuario,
    editar_usuario,
    listar_auditoria,
    listar_usuarios,
    normalizar_correo,
    resetear_password,
    validar_password,
)
from src.core.security import hash_password, verify_password

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requiere DATABASE_URL (pruebas de integración).",
)

PASSWORD = "Clave1234"


def _correo(prefijo="pytest_usuario"):
    return f"{prefijo}_{uuid4().hex[:8]}@example.com"


@pytest.fixture
def contexto():
    """Crea un ejecutor IT temporal y limpia todo lo generado al final."""
    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")

    creados = []
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id_rol FROM rol WHERE nombre_rol = 'IT'")
                fila = cursor.fetchone()
                if not fila:
                    pytest.skip(
                        "Falta el rol IT; ejecute scripts/migracion_fase9.py."
                    )
                id_rol = fila[0]

                correo_actor = _correo("pytest_it")
                cursor.execute(
                    """
                    INSERT INTO usuario
                        (id_rol, nombre_completo, correo_institucional,
                         password_hash, estado_vigencia, ultima_actividad)
                    VALUES (%s, %s, %s, %s, TRUE, NOW())
                    RETURNING id_usuario
                    """,
                    (
                        id_rol,
                        "PYTEST IT TEMPORAL",
                        correo_actor,
                        hash_password(PASSWORD),
                    ),
                )
                id_actor = cursor.fetchone()[0]

        creados.append(id_actor)
        yield {
            "actor": id_actor,
            "actor_nombre": "PYTEST IT TEMPORAL",
            "actor_correo": correo_actor,
            "creados": creados,
        }
    finally:
        conn = get_connection()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            DELETE FROM usuario_log
                            WHERE id_ejecutor = ANY(%s) OR id_afectado = ANY(%s)
                            """,
                            (creados, creados),
                        )
                        cursor.execute(
                            "DELETE FROM usuario WHERE id_usuario = ANY(%s)",
                            (creados,),
                        )
            finally:
                conn.close()


def _crear(contexto, correo=None, rol="Consultor", dias=15):
    id_usuario = crear_usuario(
        contexto["actor"],
        "USUARIO PYTEST",
        correo or _correo(),
        rol,
        PASSWORD,
        dias,
    )
    contexto["creados"].append(id_usuario)
    return id_usuario


def _fila(id_usuario):
    df = listar_usuarios()
    return df[df["id_usuario"] == id_usuario].iloc[0]


def test_validar_password_aplica_la_politica():
    assert validar_password("Clave1234") == "Clave1234"
    for invalida in ("Ab1", "sololetras", "12345678"):
        with pytest.raises(DatosInvalidos):
            validar_password(invalida)


def test_normalizar_correo_rechaza_formatos_invalidos():
    assert normalizar_correo("  Persona@Banco.COM ") == "persona@banco.com"
    for invalido in ("sin-arroba", "sin@dominio", "con espacio@x.com", ""):
        with pytest.raises(DatosInvalidos):
            normalizar_correo(invalido)


def test_solo_it_puede_gestionar_usuarios(contexto):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id_usuario FROM usuario u
                JOIN rol r ON u.id_rol = r.id_rol
                WHERE r.nombre_rol = 'Administrador'
                  AND u.estado_vigencia = TRUE
                ORDER BY u.id_usuario LIMIT 1
                """
            )
            fila = cursor.fetchone()
    finally:
        conn.close()

    if not fila:
        pytest.skip("No hay un Administrador activo para la prueba.")

    with pytest.raises(OperacionNoPermitida):
        crear_usuario(
            fila[0],
            "NO DEBE CREARSE",
            _correo(),
            "Consultor",
            PASSWORD,
        )


def test_crear_usuario_normaliza_y_aparece_en_el_listado(contexto):
    correo = _correo().upper()
    id_usuario = _crear(contexto, correo=correo, dias=20)

    fila = _fila(id_usuario)
    assert fila["correo_institucional"] == correo.lower()
    assert fila["nombre_rol"] == "Consultor"
    assert bool(fila["estado_vigencia"]) is True
    assert int(fila["dias_vacaciones_asignados"]) == 20
    assert int(fila["dias_disponibles"]) == 20


def test_correo_duplicado_es_rechazado(contexto):
    correo = _correo()
    _crear(contexto, correo=correo)

    with pytest.raises(CorreoDuplicado):
        crear_usuario(
            contexto["actor"],
            "OTRA PERSONA",
            correo.upper(),
            "Consultor",
            PASSWORD,
        )


def test_correo_invalido_es_rechazado(contexto):
    with pytest.raises(DatosInvalidos):
        crear_usuario(
            contexto["actor"],
            "PERSONA INVALIDA",
            "sin-arroba",
            "Consultor",
            PASSWORD,
        )


def test_editar_usuario_actualiza_datos_y_rol(contexto):
    id_usuario = _crear(contexto)
    nuevo_correo = _correo("pytest_editado")

    editar_usuario(
        contexto["actor"],
        id_usuario,
        "NOMBRE EDITADO",
        nuevo_correo,
        "Coordinador GTC",
        10,
    )

    fila = _fila(id_usuario)
    assert fila["nombre_completo"] == "NOMBRE EDITADO"
    assert fila["correo_institucional"] == nuevo_correo
    assert fila["nombre_rol"] == "Coordinador GTC"
    assert int(fila["dias_vacaciones_asignados"]) == 10


def test_baja_logica_y_reactivacion(contexto):
    id_usuario = _crear(contexto)

    cambiar_estado_usuario(contexto["actor"], id_usuario, False)
    assert bool(_fila(id_usuario)["estado_vigencia"]) is False

    cambiar_estado_usuario(contexto["actor"], id_usuario, True)
    assert bool(_fila(id_usuario)["estado_vigencia"]) is True


def test_reset_password_cambia_el_hash(contexto):
    id_usuario = _crear(contexto)
    nueva = "NuevaClave9"

    resetear_password(contexto["actor"], id_usuario, nueva)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT password_hash FROM usuario WHERE id_usuario = %s",
                (id_usuario,),
            )
            almacenado = cursor.fetchone()[0]
    finally:
        conn.close()

    assert verify_password(nueva, almacenado)
    assert not verify_password(PASSWORD, almacenado)


def test_no_puede_desactivarse_a_si_mismo(contexto):
    with pytest.raises(OperacionNoPermitida):
        cambiar_estado_usuario(contexto["actor"], contexto["actor"], False)


def test_no_puede_cambiarse_el_rol_a_si_mismo(contexto):
    with pytest.raises(OperacionNoPermitida):
        editar_usuario(
            contexto["actor"],
            contexto["actor"],
            contexto["actor_nombre"],
            contexto["actor_correo"],
            "Consultor",
            15,
        )


def test_ultimo_administrador_activo_esta_protegido(contexto):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id_usuario
                FROM usuario u
                JOIN rol r ON u.id_rol = r.id_rol
                WHERE r.nombre_rol = 'Administrador'
                  AND u.estado_vigencia = TRUE
                """
            )
            administradores = [fila[0] for fila in cursor.fetchall()]
    finally:
        conn.close()

    if len(administradores) != 1:
        pytest.skip("La base no tiene exactamente un Administrador activo.")

    with pytest.raises(OperacionNoPermitida):
        cambiar_estado_usuario(
            contexto["actor"], administradores[0], False
        )


def test_auditoria_registra_las_acciones(contexto):
    id_usuario = _crear(contexto)
    editar_usuario(
        contexto["actor"],
        id_usuario,
        "AUDITADO",
        _correo("pytest_auditado"),
        "Consultor",
        15,
    )
    resetear_password(contexto["actor"], id_usuario, "OtraClave9")
    cambiar_estado_usuario(contexto["actor"], id_usuario, False)
    cambiar_estado_usuario(contexto["actor"], id_usuario, True)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT accion FROM usuario_log
                WHERE id_afectado = %s
                """,
                (id_usuario,),
            )
            acciones = {fila[0] for fila in cursor.fetchall()}
    finally:
        conn.close()

    assert {
        "CREACION",
        "EDICION",
        "RESET_PASSWORD",
        "BAJA",
        "REACTIVACION",
    }.issubset(acciones)

    auditoria = listar_auditoria()
    assert not auditoria.empty
    assert "accion" in auditoria.columns
