# Fase 11: la bandeja del Coordinador GTC muestra solo los expedientes que le
# fueron asignados (Tabla 9) y solo ese coordinador puede darles su visto bueno.
#
# Las pruebas unitarias usan dobles de prueba; las de integración se omiten si
# no hay DATABASE_URL y limpian los usuarios y solicitudes que crean.

import datetime
import os
from uuid import uuid4

import pytest

from src.core import recordatorios, solicitudes
from src.core.validaciones import ValidacionError
from src.core.workflow import (
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)
from src.features import coordinador

requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)


# ---------------------------------------------------------------------------
# Dobles de prueba
# ---------------------------------------------------------------------------
class _CursorFalso:
    def __init__(self, fila):
        self.fila = fila
        self.sentencias = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.sentencias.append(sql)

    def fetchone(self):
        return self.fila

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor
        self.cerrada = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.cerrada = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# Pruebas unitarias
# ---------------------------------------------------------------------------
def test_registro_exige_coordinador_asignado():
    with pytest.raises(ValidacionError):
        solicitudes.registrar_solicitud(
            1,
            "DUELO",
            datetime.date(2031, 3, 10),
            datetime.date(2031, 3, 11),
            None,
            "Consultor",
            "C-001",
            2,
            "Motivo",
        )


def test_otro_coordinador_no_puede_firmar(monkeypatch):
    cursor = _CursorFalso((ESTADO_PENDIENTE_FIRMA_COORDINADOR, 7))
    conexion = _ConexionFalsa(cursor)
    monkeypatch.setattr(solicitudes, "get_connection", lambda: conexion)

    with pytest.raises(solicitudes.CoordinadorNoAsignado):
        solicitudes.cambiar_estado(
            10, ESTADO_PENDIENTE_APROBACION_GERENCIA, 8, firma_b64="abc"
        )

    # Solo se leyó el expediente: no hubo UPDATE ni historial.
    assert len(cursor.sentencias) == 1
    assert "FOR UPDATE" in cursor.sentencias[0]
    assert conexion.cerrada


def test_bandeja_filtra_por_coordinador(monkeypatch):
    capturado = {}

    def leer(query, engine, params=None):
        capturado["query"] = query
        capturado["params"] = params
        return coordinador.pd.DataFrame()

    monkeypatch.setattr(coordinador, "get_engine", lambda: object())
    monkeypatch.setattr(coordinador.pd, "read_sql_query", leer)

    coordinador.obtener_solicitudes_pendientes(42)

    assert "s.id_coordinador = %s" in capturado["query"]
    assert capturado["params"] == (ESTADO_PENDIENTE_FIRMA_COORDINADOR, 42)


def test_recordatorio_sin_coordinador_no_tiene_destinatario():
    cursor = _CursorFalso(None)
    assert recordatorios._resolver_destinatario(cursor, None) is None
    assert cursor.sentencias == []


# ---------------------------------------------------------------------------
# Pruebas de integración
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
def test_expediente_solo_llega_a_su_coordinador(equipo):
    id_solicitud = solicitudes.registrar_solicitud(
        equipo["consultor"],
        "DUELO",
        datetime.date(2033, 3, 7),
        datetime.date(2033, 3, 8),
        equipo["coord_a"],
        "Consultor",
        "C-001",
        2,
        f"PYTEST_EQUIPO_{uuid4().hex[:8]}",
    )

    datos = solicitudes.obtener_solicitud(id_solicitud)
    assert datos["id_coordinador"] == equipo["coord_a"]
    assert datos["jefe_gtc"].startswith("PYTEST coord_a")

    bandeja_a = coordinador.obtener_solicitudes_pendientes(equipo["coord_a"])
    bandeja_b = coordinador.obtener_solicitudes_pendientes(equipo["coord_b"])
    assert id_solicitud in bandeja_a["id_solicitud"].tolist()
    assert id_solicitud not in bandeja_b["id_solicitud"].tolist()

    with pytest.raises(solicitudes.CoordinadorNoAsignado):
        solicitudes.cambiar_estado(
            id_solicitud,
            ESTADO_PENDIENTE_APROBACION_GERENCIA,
            equipo["coord_b"],
            firma_b64="firma",
        )
    assert solicitudes.obtener_estado(id_solicitud) == ESTADO_PENDIENTE_FIRMA_COORDINADOR

    solicitudes.cambiar_estado(
        id_solicitud,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        equipo["coord_a"],
        firma_b64="firma",
    )
    assert solicitudes.obtener_estado(id_solicitud) == ESTADO_PENDIENTE_APROBACION_GERENCIA


@requiere_bd
def test_registro_rechaza_jefe_que_no_es_coordinador(equipo):
    with pytest.raises(ValidacionError):
        solicitudes.registrar_solicitud(
            equipo["consultor"],
            "DUELO",
            datetime.date(2033, 3, 7),
            datetime.date(2033, 3, 8),
            equipo["consultor"],
            "Consultor",
            "C-001",
            2,
            "PYTEST_JEFE_INVALIDO",
        )
