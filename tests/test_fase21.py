# Fase 21: indicadores del dashboard y catálogo mantenible de motivos.

import datetime
import os

import pandas as pd
import pytest

from src.core import indicadores, motivos
from src.core.indicadores import calcular_tiempos, formatear_duracion, resumen_usuarios
from src.core.motivos import MotivoError, normalizar_nombre

requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)


# ---------------------------------------------------------------------------
# Tiempos de aprobación
# ---------------------------------------------------------------------------
def _ts(dia, hora=0):
    return pd.Timestamp(2026, 11, dia, hora)


def _resueltas():
    return pd.DataFrame({
        "fecha_creacion": [_ts(2, 8), _ts(3, 8), _ts(4, 8)],
        # 1: aprobada tras banco y Gerencia; 2: aprobada; 3: denegada por el banco
        "fecha_banco": [_ts(2, 20), _ts(4, 8), _ts(4, 14)],
        "fecha_resolucion": [_ts(3, 8), _ts(5, 8), _ts(4, 14)],
        "resolucion": ["Aprobada", "Aprobada", "Denegada"],
    })


def test_promedio_total_y_por_resolucion():
    t = calcular_tiempos(_resueltas())
    assert t["resueltas"] == 3
    # 24 h, 48 h y 6 h -> 26 h de promedio.
    assert t["total"] == pd.Timedelta(hours=26)
    assert t["aprobadas"] == pd.Timedelta(hours=36)
    assert t["denegadas"] == pd.Timedelta(hours=6)


def test_promedio_por_etapa():
    t = calcular_tiempos(_resueltas())
    # Banco: 12 h, 24 h y 6 h.
    assert t["banco"] == pd.Timedelta(hours=14)
    # Gerencia solo cuenta los que llegaron a esa etapa (12 h y 24 h).
    assert t["gerencia"] == pd.Timedelta(hours=18)


def test_sin_resueltas_no_hay_tiempos():
    assert calcular_tiempos(pd.DataFrame())["resueltas"] == 0
    assert calcular_tiempos(None)["total"] is None


@pytest.mark.parametrize(
    "duracion, texto",
    [
        (pd.Timedelta(days=2, hours=3, minutes=40), "2 d 3 h"),
        (pd.Timedelta(hours=5, minutes=20), "5 h 20 min"),
        (pd.Timedelta(minutes=45), "45 min"),
        (None, "—"),
        (pd.NaT, "—"),
    ],
)
def test_formato_de_duracion(duracion, texto):
    assert formatear_duracion(duracion) == texto


# ---------------------------------------------------------------------------
# Usuarios vigentes e inactivos
# ---------------------------------------------------------------------------
def test_resumen_de_usuarios():
    hoy = datetime.date(2026, 11, 5)
    df = pd.DataFrame({
        "nombre_rol": ["Consultor", "Consultor", "Contabilidad", "IT", "Consultor"],
        "vigente": [True, True, True, True, False],
        "fecha_actualizacion_datos": pd.to_datetime([
            "2026-05-20",   # vence 20/11: por vencer
            "2026-10-01",   # vence en abril: no
            "2026-05-10",   # vence 10/11: por vencer
            "2025-01-01",   # IT no actualiza datos: no cuenta
            "2026-05-20",   # inactivo: no cuenta
        ]),
    })
    r = resumen_usuarios(df, hoy)
    assert (r["total"], r["vigentes"], r["inactivos"]) == (5, 4, 1)
    assert r["pct_inactivos"] == 20.0
    assert r["por_vencer"] == 2


def test_resumen_sin_usuarios():
    assert resumen_usuarios(pd.DataFrame())["total"] == 0


# ---------------------------------------------------------------------------
# Catálogo de motivos
# ---------------------------------------------------------------------------
def test_nombre_se_normaliza():
    assert normalizar_nombre("  permiso   por   estudio ") == "PERMISO POR ESTUDIO"


@pytest.mark.parametrize("nombre", ["", "ab", "x" * (motivos.NOMBRE_MAX + 1)])
def test_nombre_invalido(nombre):
    with pytest.raises(MotivoError):
        normalizar_nombre(nombre)


def test_si_el_catalogo_falla_se_usa_la_lista_de_la_plantilla(monkeypatch):
    def falla(solo_activos=False):
        raise RuntimeError("sin base")

    monkeypatch.setattr(motivos, "listar_motivos", falla)
    assert "VACACION" in motivos.opciones_activas()
    assert len(motivos.opciones_activas()) == 22


def test_la_cuadricula_del_pdf_coincide_con_el_catalogo_base():
    from src.core.catalogos import OPCIONES_AUSENCIA
    from src.services.motor_pdf import CUADRICULA

    en_hoja = [o for fila in CUADRICULA for o in fila[1:] if o]
    assert sorted(en_hoja) == sorted(OPCIONES_AUSENCIA)


# ---------------------------------------------------------------------------
# Catálogo contra Supabase (transacción revertida; incluye la tabla nueva)
# ---------------------------------------------------------------------------
@pytest.fixture
def catalogo(monkeypatch):
    from pathlib import Path

    from scripts.migracion_fase21 import DDL, sembrar
    from transaccion import transaccion_revertida

    triggers = (
        Path(__file__).resolve().parents[1] / "docs" / "triggers.sql"
    ).read_text(encoding="utf-8")

    with transaccion_revertida(monkeypatch, motivos, ddl=[*DDL, triggers]) as cursor:
        sembrar(cursor)
        cursor.execute(
            """
            INSERT INTO usuario (id_rol, nombre_completo, correo_institucional,
                                 password_hash, estado_vigencia, ultima_actividad)
            SELECT id_rol, 'PYTEST Gerencia', 'pytest_g_' || md5(random()::text),
                   'x', TRUE, NOW() FROM rol WHERE nombre_rol = 'Administrador'
            RETURNING id_usuario
            """
        )
        gerencia = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO usuario (id_rol, nombre_completo, correo_institucional,
                                 password_hash, estado_vigencia, ultima_actividad)
            SELECT id_rol, 'PYTEST Consultor', 'pytest_c_' || md5(random()::text),
                   'x', TRUE, NOW() FROM rol WHERE nombre_rol = 'Consultor'
            RETURNING id_usuario
            """
        )
        yield {"cursor": cursor, "gerencia": gerencia, "consultor": cursor.fetchone()[0]}


def _id_motivo(cursor, nombre):
    cursor.execute("SELECT id_motivo FROM motivo_ausencia WHERE nombre = %s", (nombre,))
    return cursor.fetchone()[0]


@requiere_bd
def test_se_siembran_los_22_motivos_y_se_protegen_dos(catalogo):
    cursor = catalogo["cursor"]
    cursor.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE protegido) FROM motivo_ausencia "
                   "WHERE en_plantilla")
    assert cursor.fetchone() == (22, 2)


@requiere_bd
def test_gerencia_agrega_un_motivo_nuevo(catalogo):
    nombre = motivos.crear_motivo(catalogo["gerencia"], " permiso por estudio ")
    assert nombre == "PERMISO POR ESTUDIO"
    with pytest.raises(MotivoError, match="Ya existe"):
        motivos.crear_motivo(catalogo["gerencia"], "Permiso por ESTUDIO")


@requiere_bd
def test_solo_gerencia_mantiene_el_catalogo(catalogo):
    with pytest.raises(MotivoError, match="Solo Gerencia"):
        motivos.crear_motivo(catalogo["consultor"], "PERMISO NUEVO")


@requiere_bd
def test_desactivar_y_reactivar(catalogo):
    cursor = catalogo["cursor"]
    id_duelo = _id_motivo(cursor, "DUELO")
    motivos.cambiar_estado_motivo(catalogo["gerencia"], id_duelo, False)
    cursor.execute("SELECT activo FROM motivo_ausencia WHERE id_motivo = %s", (id_duelo,))
    assert cursor.fetchone()[0] is False
    motivos.cambiar_estado_motivo(catalogo["gerencia"], id_duelo, True)
    cursor.execute("SELECT activo FROM motivo_ausencia WHERE id_motivo = %s", (id_duelo,))
    assert cursor.fetchone()[0] is True


@requiere_bd
@pytest.mark.parametrize("nombre", ["VACACION", "SUSPENSIÓN IGSS"])
def test_los_motivos_con_regla_propia_no_se_desactivan(catalogo, nombre):
    id_motivo = _id_motivo(catalogo["cursor"], nombre)
    with pytest.raises(MotivoError, match="regla propia"):
        motivos.cambiar_estado_motivo(catalogo["gerencia"], id_motivo, False)


@requiere_bd
def test_la_base_impide_renombrar_borrar_y_desactivar_protegidos(catalogo):
    import psycopg2

    cursor = catalogo["cursor"]
    cursor.execute("SAVEPOINT sp")
    for sql in (
        "UPDATE motivo_ausencia SET nombre = 'OTRO' WHERE nombre = 'DUELO'",
        "DELETE FROM motivo_ausencia WHERE nombre = 'DUELO'",
        "UPDATE motivo_ausencia SET activo = FALSE WHERE nombre = 'VACACION'",
    ):
        with pytest.raises(psycopg2.Error, match="SETESA"):
            cursor.execute(sql)
        cursor.execute("ROLLBACK TO SAVEPOINT sp")


@requiere_bd
def test_no_se_registra_un_motivo_desactivado(catalogo):
    import psycopg2

    cursor = catalogo["cursor"]
    cursor.execute("UPDATE motivo_ausencia SET activo = FALSE WHERE nombre = 'DUELO'")
    cursor.execute(
        """
        INSERT INTO usuario (id_rol, nombre_completo, correo_institucional,
                             password_hash, estado_vigencia, ultima_actividad)
        SELECT id_rol, 'PYTEST Coord', 'pytest_k_' || md5(random()::text),
               'x', TRUE, NOW() FROM rol WHERE nombre_rol = 'Coordinador GTC'
        RETURNING id_usuario
        """
    )
    coord = cursor.fetchone()[0]
    sql = (
        "INSERT INTO solicitud (id_usuario, tipo_ausencia, fecha_inicio, fecha_fin, "
        "estado_workflow, id_coordinador) VALUES (%s, %s, DATE '2036-03-03', "
        "DATE '2036-03-04', 'Ingresada', %s)"
    )
    cursor.execute("SAVEPOINT sp")
    with pytest.raises(psycopg2.Error, match="catálogo"):
        cursor.execute(sql, (catalogo["consultor"], "DUELO", coord))
    cursor.execute("ROLLBACK TO SAVEPOINT sp")
    cursor.execute(sql, (catalogo["consultor"], "MATRIMONIO", coord))  # activo: sí
