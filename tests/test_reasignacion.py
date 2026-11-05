# Fase 12: Gerencia reasigna expedientes a otro Coordinador GTC.
#
# Las pruebas unitarias usan dobles de prueba; las de integración se omiten si
# no hay DATABASE_URL y eliminan los usuarios y solicitudes que crean.

import datetime
import os
from uuid import uuid4

import pytest

from src.core import reasignacion, solicitudes
from src.core.workflow import (
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)
from src.features import coordinador

requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)


class _CursorFalso:
    """Devuelve las filas indicadas, en orden, a cada fetchone()."""

    def __init__(self, filas):
        self.filas = list(filas)
        self.sentencias = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.sentencias.append(sql)

    def fetchone(self):
        return self.filas.pop(0) if self.filas else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _con_filas(monkeypatch, filas):
    cursor = _CursorFalso(filas)
    monkeypatch.setattr(
        reasignacion, "get_connection", lambda: _ConexionFalsa(cursor)
    )
    return cursor


def test_motivo_obligatorio():
    with pytest.raises(reasignacion.ReasignacionError, match="motivo"):
        reasignacion.reasignar_coordinador(1, 2, 3, "   ")


def test_solo_expedientes_pendientes_del_banco(monkeypatch):
    cursor = _con_filas(
        monkeypatch, [(ESTADO_PENDIENTE_APROBACION_GERENCIA, 5, "Coord A")]
    )
    with pytest.raises(reasignacion.ReasignacionError, match="Solo se reasignan"):
        reasignacion.reasignar_coordinador(1, 6, 3, "Baja del coordinador")
    assert not any(s.strip().startswith("UPDATE") for s in cursor.sentencias)


def test_no_reasigna_al_mismo_coordinador(monkeypatch):
    _con_filas(monkeypatch, [(ESTADO_PENDIENTE_FIRMA_COORDINADOR, 5, "Coord A")])
    with pytest.raises(reasignacion.ReasignacionError, match="ya está asignado"):
        reasignacion.reasignar_coordinador(1, 5, 3, "Motivo")


def test_nuevo_debe_ser_coordinador_vigente(monkeypatch):
    cursor = _con_filas(
        monkeypatch,
        [(ESTADO_PENDIENTE_FIRMA_COORDINADOR, 5, "Coord A"), None],
    )
    with pytest.raises(reasignacion.ReasignacionError, match="vigente"):
        reasignacion.reasignar_coordinador(1, 6, 3, "Motivo")
    assert not any(s.strip().startswith("UPDATE") for s in cursor.sentencias)


# ---------------------------------------------------------------------------
# Integración
# ---------------------------------------------------------------------------
def _crear_usuario(cursor, rol, prefijo):
    cursor.execute("SELECT id_rol FROM rol WHERE nombre_rol = %s", (rol,))
    fila = cursor.fetchone()
    if not fila:
        pytest.skip(f"No existe el rol {rol}.")
    marca = uuid4().hex[:8]
    cursor.execute(
        """
        INSERT INTO usuario
            (id_rol, nombre_completo, correo_institucional, password_hash,
             estado_vigencia, ultima_actividad)
        VALUES (%s, %s, %s, 'x', TRUE, NOW())
        RETURNING id_usuario
        """,
        (fila[0], f"PYTEST {prefijo} {marca}", f"pytest_{prefijo}_{marca}@example.com"),
    )
    return cursor.fetchone()[0]


@pytest.fixture
def equipo():
    from src.core.database import get_connection

    conn = get_connection()
    if not conn:
        pytest.skip("No hay conexión a la base de datos.")
    try:
        with conn:
            with conn.cursor() as cursor:
                ids = {
                    "consultor": _crear_usuario(cursor, "Consultor", "consultor"),
                    "gerencia": _crear_usuario(cursor, "Administrador", "gerencia"),
                    "coord_a": _crear_usuario(cursor, "Coordinador GTC", "coord_a"),
                    "coord_b": _crear_usuario(cursor, "Coordinador GTC", "coord_b"),
                }
    finally:
        conn.close()

    yield ids

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM solicitud WHERE id_usuario = %s",
                    (ids["consultor"],),
                )
                cursor.execute(
                    "DELETE FROM usuario WHERE id_usuario = ANY(%s)",
                    (list(ids.values()),),
                )
    finally:
        conn.close()


@requiere_bd
def test_reasignacion_mueve_el_expediente_de_bandeja(equipo):
    id_solicitud = solicitudes.registrar_solicitud(
        equipo["consultor"],
        "DUELO",
        datetime.date(2033, 5, 9),
        datetime.date(2033, 5, 10),
        equipo["coord_a"],
        "Consultor",
        "C-001",
        2,
        f"PYTEST_REASIGNACION_{uuid4().hex[:8]}",
    )
    assert reasignacion.contar_pendientes_coordinador(equipo["coord_a"]) == 1

    resultado = reasignacion.reasignar_coordinador(
        id_solicitud, equipo["coord_b"], equipo["gerencia"], "Baja del coordinador"
    )
    assert resultado["nuevo"].startswith("PYTEST coord_b")

    bandeja_a = coordinador.obtener_solicitudes_pendientes(equipo["coord_a"])
    bandeja_b = coordinador.obtener_solicitudes_pendientes(equipo["coord_b"])
    assert id_solicitud not in bandeja_a["id_solicitud"].tolist()
    assert id_solicitud in bandeja_b["id_solicitud"].tolist()

    datos = solicitudes.obtener_solicitud(id_solicitud)
    assert datos["jefe_gtc"] == resultado["nuevo"]
    assert datos["estado_workflow"] == ESTADO_PENDIENTE_FIRMA_COORDINADOR

    historial = solicitudes.obtener_historial(id_solicitud)
    assert "Reasignada" in historial["observacion"].iloc[-1]

    # El coordinador anterior ya no puede firmar; el nuevo sí.
    with pytest.raises(solicitudes.CoordinadorNoAsignado):
        solicitudes.cambiar_estado(
            id_solicitud,
            ESTADO_PENDIENTE_APROBACION_GERENCIA,
            equipo["coord_a"],
            firma_b64="firma",
        )
    solicitudes.cambiar_estado(
        id_solicitud,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        equipo["coord_b"],
        firma_b64="firma",
    )
