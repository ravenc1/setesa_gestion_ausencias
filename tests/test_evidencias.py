# Fase 18: evidencias adjuntas y avisos al finalizar.

import datetime

import pytest

from src.core import evidencias as ev
from src.core import notificaciones, solicitudes
from src.core.validaciones import ValidacionError
from src.services import almacenamiento

PDF = b"%PDF-1.4\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
JPG = b"\xff\xd8\xff\xe0" + b"0" * 20


@pytest.mark.parametrize(
    "nombre, contenido, tipo",
    [
        ("constancia.pdf", PDF, "application/pdf"),
        ("foto.PNG", PNG, "image/png"),
        ("foto.jpeg", JPG, "image/jpeg"),
        ("foto.jpg", JPG, "image/jpeg"),
    ],
)
def test_acepta_pdf_png_jpg(nombre, contenido, tipo):
    assert ev.validar_archivo(nombre, contenido)[0] == tipo


@pytest.mark.parametrize(
    "nombre, contenido, mensaje",
    [
        ("vacio.pdf", b"", "vacío"),
        ("documento.docx", PDF, "solo se aceptan"),
        ("sin_extension", PDF, "solo se aceptan"),
        ("falso.pdf", PNG, "no coincide"),
        ("texto.pdf", b"hola", "no es un PDF"),
    ],
)
def test_rechaza_archivos_invalidos(nombre, contenido, mensaje):
    with pytest.raises(ev.EvidenciaError, match=mensaje):
        ev.validar_archivo(nombre, contenido)


def test_rechaza_archivos_de_mas_de_5_mb():
    with pytest.raises(ev.EvidenciaError, match="5 MB"):
        ev.validar_archivo("grande.pdf", b"%PDF" + b"0" * ev.TAMANO_MAXIMO)


def test_igss_es_la_unica_obligatoria():
    assert ev.evidencia_obligatoria("SUSPENSIÓN IGSS")
    assert not ev.evidencia_obligatoria("VACACION")


def test_registro_igss_sin_evidencia_se_rechaza_antes_de_la_base():
    with pytest.raises(ValidacionError, match="IGSS"):
        solicitudes.registrar_solicitud(
            1, "SUSPENSIÓN IGSS", datetime.date(2031, 3, 10),
            datetime.date(2031, 3, 11), 5, "Consultor", "C-001", 2, "Motivo",
        )


def test_subir_evidencias_al_repositorio(tmp_path, monkeypatch):
    monkeypatch.setattr(almacenamiento, "REPOSITORIO_DIR", tmp_path)
    monkeypatch.setattr(almacenamiento, "configuracion_supabase", lambda: None)
    subidas = ev.subir_evidencias([("constancia.pdf", PDF), ("foto.png", PNG)])
    assert [s["tipo_mime"] for s in subidas] == ["application/pdf", "image/png"]
    assert all(s["clave"].startswith("evidencias/") for s in subidas)
    assert almacenamiento.leer(subidas[0]["clave"]) == PDF
    assert len(subidas[0]["sha256"]) == 64


def test_un_archivo_invalido_no_sube_ninguno(tmp_path, monkeypatch):
    monkeypatch.setattr(almacenamiento, "REPOSITORIO_DIR", tmp_path)
    monkeypatch.setattr(almacenamiento, "configuracion_supabase", lambda: None)
    with pytest.raises(ev.EvidenciaError):
        ev.subir_evidencias([("constancia.pdf", PDF), ("virus.exe", b"MZ")])
    assert not list(tmp_path.rglob("*.pdf"))


class _Cursor:
    def __init__(self, fila):
        self.fila = fila

    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return self.fila


@pytest.mark.parametrize(
    "fila, id_usuario, permitido",
    [
        ((7, "Consultor"), 7, True),       # consultor dueño
        ((7, "Consultor"), 8, False),      # otro consultor
        ((7, "Contabilidad"), 9, True),    # Contabilidad y RR.HH.
        ((7, "Administrador"), 3, True),   # Gerencia
        ((7, "Coordinador GTC"), 5, False),  # el banco no ve evidencias
        ((7, "IT"), 2, False),
    ],
)
def test_quien_puede_ver_evidencias(fila, id_usuario, permitido):
    assert ev._puede_ver(_Cursor(fila), 1, id_usuario) is permitido


def test_enlace_de_correo_al_consultor():
    enlace = notificaciones.enlace_al_consultor({
        "correo_consultor": "ana@example.com",
        "consultor": "Ana López",
        "id_solicitud": 12,
        "mensaje": "Expediente #12 de Ana López (VACACION): APROBADA.",
    })
    assert enlace.startswith("mailto:ana@example.com?subject=")
    assert "%2312" in enlace  # "#12" codificado
