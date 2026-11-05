# Fase 13: triggers de PostgreSQL (docs/triggers.sql).
#
# Todo ocurre en UNA transacción que se revierte al final: se aplican los
# triggers, se crean usuarios y solicitudes de prueba y se intentan las
# violaciones. No queda nada guardado en la base. Se omite sin DATABASE_URL.

import os
from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)

SQL_TRIGGERS = (
    Path(__file__).resolve().parents[1] / "docs" / "triggers.sql"
).read_text(encoding="utf-8")

PEND_COORD = "Pendiente de Firma Coordinador"
PEND_GER = "Pendiente de Aprobación Gerencia"
FINALIZADA = "Finalizada"


@pytest.fixture
def cur():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cursor = conn.cursor()
    try:
        # Columnas de la Fase 14, por si la base aún no está migrada.
        cursor.execute(
            "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS "
            "fecha_actualizacion_datos TIMESTAMP DEFAULT NOW()"
        )
        # Columnas de la Fase 16.
        for columna in (
            "resolucion VARCHAR(10)",
            "motivo_resolucion TEXT",
            "fecha_resolucion TIMESTAMP",
            "id_resuelve INTEGER",
        ):
            cursor.execute(
                f"ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS {columna}"
            )
        cursor.execute(SQL_TRIGGERS)
        yield cursor
    finally:
        conn.rollback()
        cursor.close()
        conn.close()


def _rechaza(cur, sql, params=None):
    """True si la sentencia es rechazada por un trigger de SETESA."""
    cur.execute("SAVEPOINT sp")
    try:
        cur.execute(sql, params)
    except psycopg2.Error as e:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
        return "SETESA" in str(e)
    cur.execute("RELEASE SAVEPOINT sp")
    return False


def _usuario(cur, rol, actualizado="NOW()", vigente=True):
    """Crea un usuario; ``actualizado`` es su última actualización de datos."""
    cur.execute(
        f"""
        INSERT INTO usuario
            (id_rol, nombre_completo, correo_institucional, password_hash,
             estado_vigencia, ultima_actividad, fecha_actualizacion_datos)
        SELECT id_rol, 'PYTEST ' || %s, 'pytest_trg_' || md5(random()::text)
               || '@example.com', 'x', %s, NOW(), {actualizado}
          FROM rol WHERE nombre_rol = %s
        RETURNING id_usuario
        """,
        (rol, vigente, rol),
    )
    fila = cur.fetchone()
    if not fila:
        pytest.skip(f"No existe el rol {rol}.")
    return fila[0]


@pytest.fixture
def actores(cur):
    return {
        "consultor": _usuario(cur, "Consultor"),
        "coord": _usuario(cur, "Coordinador GTC"),
        "coord_otro": _usuario(cur, "Coordinador GTC"),
        "gerencia": _usuario(cur, "Administrador"),
    }


INSERT_SOLICITUD = """
    INSERT INTO solicitud
        (id_usuario, tipo_ausencia, fecha_inicio, fecha_fin,
         estado_workflow, id_coordinador)
    VALUES (%s, 'DUELO', DATE '2034-01-09', DATE '2034-01-10', %s, %s)
    RETURNING id_solicitud
"""


def _historial(cur, id_sol, anterior, nuevo, actor):
    cur.execute(
        """
        INSERT INTO solicitud_historial
            (id_solicitud, estado_anterior, estado_nuevo, id_usuario)
        VALUES (%s, %s, %s, %s)
        """,
        (id_sol, anterior, nuevo, actor),
    )


def _solicitud_pendiente(cur, a):
    cur.execute(INSERT_SOLICITUD, (a["consultor"], "Ingresada", a["coord"]))
    id_sol = cur.fetchone()[0]
    _historial(cur, id_sol, None, "Ingresada", a["consultor"])
    cur.execute(
        "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
        (PEND_COORD, id_sol),
    )
    _historial(cur, id_sol, "Ingresada", PEND_COORD, a["consultor"])
    return id_sol


def _finalizar(cur, a, id_sol):
    cur.execute(
        "UPDATE solicitud SET estado_workflow = %s, firma_jefe_gtc = 'f' "
        "WHERE id_solicitud = %s",
        (PEND_GER, id_sol),
    )
    _historial(cur, id_sol, PEND_COORD, PEND_GER, a["coord"])
    cur.execute(
        "UPDATE solicitud SET estado_workflow = %s, firma_gerencia = 'f', "
        "resolucion = 'Aprobada' WHERE id_solicitud = %s",
        (FINALIZADA, id_sol),
    )
    _historial(cur, id_sol, PEND_GER, FINALIZADA, a["gerencia"])


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
def test_registro_debe_nacer_ingresada(cur, actores):
    assert _rechaza(cur, INSERT_SOLICITUD, (actores["consultor"], FINALIZADA, actores["coord"]))


def test_registro_rechaza_usuario_dado_de_baja(cur, actores):
    inactivo = _usuario(cur, "Consultor", vigente=False)
    assert _rechaza(cur, INSERT_SOLICITUD, (inactivo, "Ingresada", actores["coord"]))


def test_registro_rechaza_usuario_vencido_sin_depurar(cur, actores):
    vencido = _usuario(cur, "Consultor", actualizado="NOW() - INTERVAL '7 months'")
    assert _rechaza(cur, INSERT_SOLICITUD, (vencido, "Ingresada", actores["coord"]))


def test_registro_exige_coordinador_gtc(cur, actores):
    assert _rechaza(
        cur, INSERT_SOLICITUD, (actores["consultor"], "Ingresada", actores["consultor"])
    )


def test_solicitud_sin_historial_se_revierte(cur, actores):
    cur.execute(INSERT_SOLICITUD, (actores["consultor"], "Ingresada", actores["coord"]))
    assert _rechaza(cur, "SET CONSTRAINTS trg_solicitud_con_historial IMMEDIATE")


# ---------------------------------------------------------------------------
# Transiciones y firmas
# ---------------------------------------------------------------------------
def test_no_se_salta_estados(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(
        cur,
        "UPDATE solicitud SET estado_workflow = %s, firma_gerencia = 'f' "
        "WHERE id_solicitud = %s",
        (FINALIZADA, id_sol),
    )


def test_visto_bueno_exige_firma(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(
        cur,
        "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
        (PEND_GER, id_sol),
    )


def test_solo_el_coordinador_asignado_registra_el_visto_bueno(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    cur.execute(
        "UPDATE solicitud SET estado_workflow = %s, firma_jefe_gtc = 'f' "
        "WHERE id_solicitud = %s",
        (PEND_GER, id_sol),
    )
    assert _rechaza(
        cur,
        "INSERT INTO solicitud_historial (id_solicitud, estado_anterior, "
        "estado_nuevo, id_usuario) VALUES (%s, %s, %s, %s)",
        (id_sol, PEND_COORD, PEND_GER, actores["coord_otro"]),
    )


def test_reasignacion_solo_a_coordinador_vigente(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(
        cur,
        "UPDATE solicitud SET id_coordinador = %s WHERE id_solicitud = %s",
        (actores["consultor"], id_sol),
    )
    assert not _rechaza(
        cur,
        "UPDATE solicitud SET id_coordinador = %s WHERE id_solicitud = %s",
        (actores["coord_otro"], id_sol),
    )


# ---------------------------------------------------------------------------
# Expediente finalizado e historial
# ---------------------------------------------------------------------------
def test_finalizada_es_inalterable_salvo_sello_pdf(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    _finalizar(cur, actores, id_sol)
    assert _rechaza(
        cur,
        "UPDATE solicitud SET explicacion = 'otra' WHERE id_solicitud = %s",
        (id_sol,),
    )
    assert not _rechaza(
        cur,
        "UPDATE solicitud SET pdf_hash = 'abc', pdf_hash_fecha = NOW() "
        "WHERE id_solicitud = %s",
        (id_sol,),
    )


def test_expediente_no_se_elimina(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(cur, "DELETE FROM solicitud WHERE id_solicitud = %s", (id_sol,))

    cur.execute("SET LOCAL setesa.permitir_borrado = 'on'")
    assert not _rechaza(cur, "DELETE FROM solicitud WHERE id_solicitud = %s", (id_sol,))


def test_historial_es_inmutable(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(
        cur,
        "UPDATE solicitud_historial SET observacion = 'x' WHERE id_solicitud = %s",
        (id_sol,),
    )
    assert _rechaza(
        cur, "DELETE FROM solicitud_historial WHERE id_solicitud = %s", (id_sol,)
    )


# ---------------------------------------------------------------------------
# Vigencia automática (sección 3.6)
# ---------------------------------------------------------------------------
def test_actividad_de_usuario_vencido_aplica_baja_logica(cur):
    vencido = _usuario(cur, "Consultor", actualizado="NOW() - INTERVAL '7 months'")
    cur.execute(
        "UPDATE usuario SET ultima_actividad = NOW() + INTERVAL '1 second' "
        "WHERE id_usuario = %s",
        (vencido,),
    )
    cur.execute(
        "SELECT estado_vigencia, fecha_actualizacion_datos < NOW() - INTERVAL '6 months' "
        "FROM usuario WHERE id_usuario = %s",
        (vencido,),
    )
    assert cur.fetchone() == (False, True)

    cur.execute(
        "SELECT COUNT(*) FROM vigencia_log WHERE detalle LIKE %s",
        (f"trigger: id={vencido} %",),
    )
    assert cur.fetchone()[0] == 1


def test_actualizar_datos_a_tiempo_renueva_el_plazo(cur):
    a_tiempo = _usuario(cur, "Consultor", actualizado="NOW() - INTERVAL '5 months'")
    cur.execute(
        "UPDATE usuario SET fecha_actualizacion_datos = NOW() WHERE id_usuario = %s",
        (a_tiempo,),
    )
    cur.execute(
        "SELECT estado_vigencia, setesa_usuario_vigente(%s) FROM usuario "
        "WHERE id_usuario = %s",
        (a_tiempo, a_tiempo),
    )
    assert cur.fetchone() == (True, True)


def test_contabilidad_tambien_vence(cur):
    conta = _usuario(cur, "Contabilidad", actualizado="NOW() - INTERVAL '7 months'")
    cur.execute("SELECT setesa_usuario_vigente(%s)", (conta,))
    assert cur.fetchone()[0] is False


@pytest.mark.parametrize("rol", ["Coordinador GTC", "Administrador", "IT"])
def test_roles_sin_actualizacion_no_vencen(cur, rol):
    usuario = _usuario(cur, rol, actualizado="NOW() - INTERVAL '7 months'")
    cur.execute(
        "UPDATE usuario SET ultima_actividad = NOW() + INTERVAL '1 second' "
        "WHERE id_usuario = %s",
        (usuario,),
    )
    cur.execute(
        "SELECT estado_vigencia, setesa_usuario_vigente(%s) FROM usuario "
        "WHERE id_usuario = %s",
        (usuario, usuario),
    )
    assert cur.fetchone() == (True, True)


def test_depuracion_programada(cur):
    vencido = _usuario(cur, "Consultor", actualizado="NOW() - INTERVAL '7 months'")
    reciente = _usuario(cur, "Consultor")
    coordinador = _usuario(
        cur, "Coordinador GTC", actualizado="NOW() - INTERVAL '7 months'"
    )
    cur.execute("SELECT setesa_depurar_vigencia()")
    assert cur.fetchone()[0] >= 1
    cur.execute(
        "SELECT id_usuario, estado_vigencia FROM usuario "
        "WHERE id_usuario IN (%s, %s, %s)",
        (vencido, reciente, coordinador),
    )
    assert dict(cur.fetchall()) == {
        vencido: False,
        reciente: True,
        coordinador: True,
    }


def test_it_puede_reasignar(cur, actores):
    it = _usuario(cur, "IT")
    id_sol = _solicitud_pendiente(cur, actores)
    cur.execute(
        "UPDATE solicitud SET id_coordinador = %s WHERE id_solicitud = %s",
        (actores["coord_otro"], id_sol),
    )
    assert not _rechaza(
        cur,
        "INSERT INTO solicitud_historial (id_solicitud, estado_anterior, "
        "estado_nuevo, id_usuario) VALUES (%s, %s, %s, %s)",
        (id_sol, PEND_COORD, PEND_COORD, it),
    )
    assert _rechaza(
        cur,
        "INSERT INTO solicitud_historial (id_solicitud, estado_anterior, "
        "estado_nuevo, id_usuario) VALUES (%s, %s, %s, %s)",
        (id_sol, PEND_COORD, PEND_COORD, actores["consultor"]),
    )


# ---------------------------------------------------------------------------
# Fase 16: resolución Aprobada / Denegada
# ---------------------------------------------------------------------------
DENEGAR_BANCO = (
    "UPDATE solicitud SET estado_workflow = 'Finalizada', firma_jefe_gtc = 'f', "
    "resolucion = 'Denegada', motivo_resolucion = %s WHERE id_solicitud = %s"
)


def test_banco_puede_denegar_con_motivo_y_firma(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert not _rechaza(cur, DENEGAR_BANCO, ("cifrado", id_sol))
    assert not _rechaza(
        cur,
        "INSERT INTO solicitud_historial (id_solicitud, estado_anterior, "
        "estado_nuevo, id_usuario) VALUES (%s, %s, %s, %s)",
        (id_sol, PEND_COORD, FINALIZADA, actores["coord"]),
    )


def test_denegacion_exige_motivo(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(cur, DENEGAR_BANCO, (None, id_sol))


def test_banco_no_puede_aprobar_y_finalizar(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(
        cur,
        "UPDATE solicitud SET estado_workflow = 'Finalizada', firma_jefe_gtc = 'f', "
        "firma_gerencia = 'f', resolucion = 'Aprobada' WHERE id_solicitud = %s",
        (id_sol,),
    )


def test_solo_el_coordinador_asignado_deniega(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    cur.execute(DENEGAR_BANCO, ("cifrado", id_sol))
    assert _rechaza(
        cur,
        "INSERT INTO solicitud_historial (id_solicitud, estado_anterior, "
        "estado_nuevo, id_usuario) VALUES (%s, %s, %s, %s)",
        (id_sol, PEND_COORD, FINALIZADA, actores["coord_otro"]),
    )


def test_finalizar_exige_resolucion(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    cur.execute(
        "UPDATE solicitud SET estado_workflow = %s, firma_jefe_gtc = 'f' "
        "WHERE id_solicitud = %s",
        (PEND_GER, id_sol),
    )
    assert _rechaza(
        cur,
        "UPDATE solicitud SET estado_workflow = 'Finalizada', firma_gerencia = 'f' "
        "WHERE id_solicitud = %s",
        (id_sol,),
    )


def test_gerencia_puede_denegar(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    cur.execute(
        "UPDATE solicitud SET estado_workflow = %s, firma_jefe_gtc = 'f' "
        "WHERE id_solicitud = %s",
        (PEND_GER, id_sol),
    )
    assert not _rechaza(
        cur,
        "UPDATE solicitud SET estado_workflow = 'Finalizada', firma_gerencia = 'f', "
        "resolucion = 'Denegada', motivo_resolucion = 'm' WHERE id_solicitud = %s",
        (id_sol,),
    )


def test_resolucion_solo_al_finalizar(cur, actores):
    id_sol = _solicitud_pendiente(cur, actores)
    assert _rechaza(
        cur,
        "UPDATE solicitud SET resolucion = 'Denegada' WHERE id_solicitud = %s",
        (id_sol,),
    )
