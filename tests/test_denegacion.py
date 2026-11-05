# Fase 16: aprobar o denegar (Coordinador GTC o Gerencia), con motivo y firma.

import os

import pytest

from src.core import solicitudes
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
    puede_denegar,
)
from src.services.motor_pdf import generar_pdf_accion_personal

MOTIVO = "El banco requiere al consultor en un proyecto urgente."


class _CursorFalso:
    def __init__(self, filas):
        self.filas = list(filas)
        self.sentencias = []
        self.parametros = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.sentencias.append(" ".join(sql.split()))
        self.parametros.append(params)

    def fetchone(self):
        return self.filas.pop(0) if self.filas else ("recordatorio",)

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


def _con_fila(monkeypatch, fila):
    cursor = _CursorFalso([fila])
    monkeypatch.setattr(solicitudes, "get_connection", lambda: _ConexionFalsa(cursor))
    monkeypatch.setattr(solicitudes, "cifrar", lambda valor: f"cif:{valor}")
    return cursor


def test_etapas_que_admiten_denegacion():
    assert puede_denegar(ESTADO_PENDIENTE_FIRMA_COORDINADOR)
    assert puede_denegar(ESTADO_PENDIENTE_APROBACION_GERENCIA)
    assert not puede_denegar(ESTADO_INGRESADA)
    assert not puede_denegar(ESTADO_FINALIZADA)


def test_motivo_obligatorio():
    with pytest.raises(solicitudes.MotivoRequerido):
        solicitudes.denegar_solicitud(1, 2, "corto", "firma")


def test_firma_obligatoria():
    with pytest.raises(solicitudes.FirmaRequerida):
        solicitudes.denegar_solicitud(1, 2, MOTIVO, "  ")


def test_banco_deniega_con_su_firma(monkeypatch):
    cursor = _con_fila(
        monkeypatch, (ESTADO_PENDIENTE_FIRMA_COORDINADOR, 7, "Coordinador GTC")
    )
    anterior = solicitudes.denegar_solicitud(10, 7, MOTIVO, "firma")
    assert anterior == ESTADO_PENDIENTE_FIRMA_COORDINADOR

    update = next(s for s in cursor.sentencias if s.startswith("UPDATE solicitud"))
    assert "firma_jefe_gtc = %s" in update
    assert "motivo_resolucion = %s" in update
    params = cursor.parametros[cursor.sentencias.index(update)]
    assert params[:4] == (ESTADO_FINALIZADA, "cif:firma", "Denegada", f"cif:{MOTIVO}")

    historial = next(s for s in cursor.sentencias if "solicitud_historial" in s)
    params_historial = cursor.parametros[cursor.sentencias.index(historial)]
    # El motivo (posible dato sensible) no se copia al historial.
    assert MOTIVO not in str(params_historial)
    # Los recordatorios al banco quedan atendidos.
    assert any(s.startswith("UPDATE recordatorio") for s in cursor.sentencias)


def test_otro_coordinador_no_deniega(monkeypatch):
    _con_fila(monkeypatch, (ESTADO_PENDIENTE_FIRMA_COORDINADOR, 7, "Coordinador GTC"))
    with pytest.raises(solicitudes.CoordinadorNoAsignado):
        solicitudes.denegar_solicitud(10, 8, MOTIVO, "firma")


def test_gerencia_deniega_con_su_firma(monkeypatch):
    cursor = _con_fila(
        monkeypatch, (ESTADO_PENDIENTE_APROBACION_GERENCIA, 7, "Administrador")
    )
    solicitudes.denegar_solicitud(10, 3, MOTIVO, "firma")
    update = next(s for s in cursor.sentencias if s.startswith("UPDATE solicitud"))
    assert "firma_gerencia = %s" in update


def test_solo_gerencia_deniega_en_su_etapa(monkeypatch):
    _con_fila(monkeypatch, (ESTADO_PENDIENTE_APROBACION_GERENCIA, 7, "Coordinador GTC"))
    with pytest.raises(solicitudes.NoAutorizadoParaDenegar):
        solicitudes.denegar_solicitud(10, 7, MOTIVO, "firma")


def test_finalizada_no_se_deniega(monkeypatch):
    _con_fila(monkeypatch, (ESTADO_FINALIZADA, 7, "Administrador"))
    with pytest.raises(solicitudes.TransicionInvalida):
        solicitudes.denegar_solicitud(10, 3, MOTIVO, "firma")


def test_pdf_de_expediente_denegado():
    ruta = generar_pdf_accion_personal(
        "QA Denegada", "Coordinador QA", "Consultor", "C-001", "VACACION",
        "2031-01-06", "2031-01-07", 2, "Explicación de prueba",
        ESTADO_FINALIZADA,
        resolucion="Denegada",
        motivo_resolucion=MOTIVO,
        denegada_por="Coordinador GTC",
    )
    try:
        assert os.path.getsize(ruta) > 0
    finally:
        os.remove(ruta)
