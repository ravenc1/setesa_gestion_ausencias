# Fase 17: repositorio persistente (local y Supabase Storage simulado).

import pytest

from src.services import almacenamiento as alm


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(alm, "REPOSITORIO_DIR", tmp_path)
    monkeypatch.setattr(alm, "configuracion_supabase", lambda: None)
    return tmp_path


def test_local_guarda_y_lee(local):
    assert alm.backend() == "local"
    alm.guardar("pdf/1/borrador.pdf", b"%PDF-1")
    assert alm.leer("pdf/1/borrador.pdf") == b"%PDF-1"
    assert (local / "pdf" / "1" / "borrador.pdf").exists()


def test_local_no_sobrescribe_si_no_se_permite(local):
    alm.guardar("pdf/1/final_x.pdf", b"a", sobrescribir=False)
    with pytest.raises(alm.ArchivoExistente):
        alm.guardar("pdf/1/final_x.pdf", b"b", sobrescribir=False)
    assert alm.leer("pdf/1/final_x.pdf") == b"a"


def test_local_archivo_inexistente(local):
    with pytest.raises(alm.ArchivoNoEncontrado):
        alm.leer("pdf/9/no.pdf")
    assert not alm.existe("pdf/9/no.pdf")


@pytest.mark.parametrize("clave", ["", "../fuera.pdf", "pdf/../../x.pdf"])
def test_rechaza_claves_invalidas(local, clave):
    with pytest.raises(alm.AlmacenamientoError):
        alm.guardar(clave, b"x")


def test_rechaza_archivos_grandes(local):
    with pytest.raises(alm.AlmacenamientoError):
        alm.guardar("pdf/1/grande.pdf", b"x" * (alm.TAMANO_MAXIMO + 1))


# ---------------------------------------------------------------------------
# Supabase Storage con respuestas simuladas
# ---------------------------------------------------------------------------
class _Respuesta:
    def __init__(self, codigo, contenido=b"", texto=""):
        self.status_code = codigo
        self.content = contenido
        self.text = texto


@pytest.fixture
def supabase(monkeypatch):
    llamadas = []
    config = {
        "url": "https://demo.supabase.co",
        "llave": "sb_secret_demo",
        "bucket": "expedientes",
    }
    monkeypatch.setattr(alm, "configuracion_supabase", lambda: config)

    def post(url, data=None, json=None, headers=None, timeout=None):
        llamadas.append(("POST", url, headers, data))
        return _Respuesta(200)

    monkeypatch.setattr(alm.requests, "post", post)
    return llamadas, config


def test_supabase_sube_al_bucket_privado(supabase):
    llamadas, _ = supabase
    alm.guardar("pdf/3/final_abc.pdf", b"%PDF", sobrescribir=False)
    metodo, url, encabezados, datos = llamadas[0]
    assert metodo == "POST"
    assert url == "https://demo.supabase.co/storage/v1/object/expedientes/pdf/3/final_abc.pdf"
    assert encabezados["x-upsert"] == "false"
    assert encabezados["apikey"] == "sb_secret_demo"
    # Una llave nueva (no JWT) no se envía como Bearer.
    assert "Authorization" not in encabezados
    assert datos == b"%PDF"


def test_supabase_llave_jwt_va_como_bearer(supabase):
    llamadas, config = supabase
    config["llave"] = "eyJhbGciOi.demo"
    alm.guardar("pdf/3/borrador.pdf", b"%PDF")
    assert llamadas[0][2]["Authorization"] == "Bearer eyJhbGciOi.demo"
    assert llamadas[0][2]["x-upsert"] == "true"


def test_supabase_lee_por_ruta_autenticada(supabase, monkeypatch):
    llamadas, _ = supabase
    monkeypatch.setattr(
        alm.requests, "get",
        lambda url, headers=None, timeout=None: (
            llamadas.append(("GET", url, headers, None)) or _Respuesta(200, b"%PDF")
        ),
    )
    assert alm.leer("pdf/3/final_abc.pdf") == b"%PDF"
    assert "/storage/v1/object/authenticated/expedientes/pdf/3/final_abc.pdf" in llamadas[0][1]


def test_supabase_errores(monkeypatch):
    config = {"url": "https://demo.supabase.co", "llave": "k", "bucket": "b"}
    monkeypatch.setattr(alm, "configuracion_supabase", lambda: config)

    monkeypatch.setattr(alm.requests, "post", lambda *a, **k: _Respuesta(409, texto="Duplicate"))
    with pytest.raises(alm.ArchivoExistente):
        alm.guardar("pdf/1/final.pdf", b"x", sobrescribir=False)

    monkeypatch.setattr(alm.requests, "post", lambda *a, **k: _Respuesta(500, texto="fallo"))
    with pytest.raises(alm.AlmacenamientoError):
        alm.guardar("pdf/1/final.pdf", b"x")

    monkeypatch.setattr(alm.requests, "get", lambda *a, **k: _Respuesta(400, texto="Object not found"))
    with pytest.raises(alm.ArchivoNoEncontrado):
        alm.leer("pdf/1/no.pdf")
