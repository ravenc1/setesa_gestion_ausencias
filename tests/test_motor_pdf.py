# Fase 19: PDF fiel a la plantilla Excel oficial de SETESA.

import datetime
import os
import re
import zlib

import pytest

from src.core.catalogos import OPCIONES_AUSENCIA
from src.services import motor_pdf
from src.services.motor_pdf import formato_fecha, generar_pdf_accion_personal


def _texto_pdf(ruta):
    """Texto de los flujos de contenido (FPDF los comprime con zlib)."""
    crudo = open(ruta, "rb").read()
    partes = []
    for flujo in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", crudo, re.S):
        try:
            partes.append(zlib.decompress(flujo))
        except zlib.error:
            partes.append(flujo)
    texto = b"".join(partes).decode("latin-1")
    # En los textos del PDF los paréntesis van escapados: \( y \).
    return texto.replace(r"\(", "(").replace(r"\)", ")"), crudo


@pytest.fixture
def pdf():
    rutas = []

    def generar(**kwargs):
        datos = dict(
            nombre_empleado="Ana López (Consultor)",
            jefe_gtc="Esmeralda Díaz",
            puesto="Analista",
            codigo="C-22",
            tipo_ausencia="VACACION",
            fecha_inicio=datetime.date(2026, 12, 14),
            fecha_fin="2026-12-18",
            dias=5,
            explicacion="Vacaciones del periodo 2026.",
            estado_workflow="Pendiente de Firma Coordinador",
            fecha_creacion="2026-11-05 10:30:00",
            id_solicitud=7,
        )
        datos.update(kwargs)
        ruta = generar_pdf_accion_personal(**datos)
        rutas.append(ruta)
        return _texto_pdf(ruta)

    yield generar
    for ruta in rutas:
        os.remove(ruta)


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (datetime.date(2026, 12, 14), "14/12/2026"),
        (datetime.datetime(2026, 1, 5, 9, 30), "05/01/2026"),
        ("2026-11-05", "05/11/2026"),
        ("2026-11-05 10:30:00", "05/11/2026"),
        (None, ""),
    ],
)
def test_fechas_en_formato_dd_mm_aaaa(valor, esperado):
    assert formato_fecha(valor) == esperado


def test_la_cuadricula_cubre_todo_el_catalogo():
    opciones = [o for fila in motor_pdf.CUADRICULA for o in fila[1:] if o]
    assert sorted(opciones) == sorted(OPCIONES_AUSENCIA)


def test_contenido_de_la_plantilla(pdf):
    texto, crudo = pdf()
    for fragmento in (
        "ACCION DE PERSONAL",
        "(NOMBRE DEL EMPLEADO)",
        "(NOMBRE DEL JEFE INMEDIATO GTC)",
        "NATURALEZA DE LA ACCION",
        "EXPLICACION DE LA ACCION",
        "NOTA: ESTE FORMULARIO DEBE LLENARSE COMPLETO",
        "JEFE INMEDIATO GTC",
        "EMPLEADO QUE SE LE APLICA",
        "Ana L\xf3pez",          # sin la etiqueta "(Consultor)"
        "14/12/2026",
        "18/12/2026",
        "05/11/2026",
        "Expediente #7",
    ):
        assert fragmento in texto, fragmento
    assert "(Consultor)" not in texto
    # Logo + firma del consultor ausente: solo el logo.
    assert crudo.count(b"/Subtype /Image") == 1


def test_marca_la_opcion_elegida(pdf):
    texto, _ = pdf(tipo_ausencia="SUSPENSIÓN IGSS")
    assert "(X) Tj" in texto


def test_denegada_por_el_banco(pdf):
    texto, _ = pdf(
        estado_workflow="Finalizada",
        resolucion="Denegada",
        motivo_resolucion="El banco requiere al consultor.",
        denegada_por="Coordinador GTC",
    )
    assert "RESOLUCION: DENEGADA POR COORDINADOR GTC" in texto
    assert "Motivo: El banco requiere al consultor." in texto
    assert "(No aplica)" in texto


def test_explicacion_larga_cabe_en_el_recuadro(pdf):
    texto, _ = pdf(explicacion="palabra " * 900)
    assert "texto completo en el sistema" in texto


def test_motivo_nuevo_se_marca_como_otros_con_su_nombre(pdf):
    texto, _ = pdf(tipo_ausencia="PERMISO POR ESTUDIO")
    assert "(PERMISO POR ESTUDIO)" in texto
    assert "(X) Tj" in texto  # la casilla de OTROS
