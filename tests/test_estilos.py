# Fase 23: identidad visual de SETESA (tema, estilos y componentes).

import tomllib
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.ui import estilos

RAIZ = Path(__file__).resolve().parents[1]


class _Streamlit:
    """Doble mínimo de `st` que recuerda el HTML recibido."""

    def __init__(self, falla=False):
        self.html = []
        self.imagenes = []
        self.falla = falla
        self.sidebar = SimpleNamespace(markdown=self.markdown, image=self.image)

    def markdown(self, texto, unsafe_allow_html=False):
        if self.falla:
            raise RuntimeError("fallo simulado")
        self.html.append(texto)

    def image(self, ruta, **_):
        self.imagenes.append(ruta)


@pytest.fixture
def st_falso(monkeypatch):
    falso = _Streamlit()
    monkeypatch.setattr(estilos, "st", falso)
    return falso


def test_los_recursos_de_marca_existen():
    assert estilos.LOGO.exists() and estilos.ICONO.exists()


def test_el_tema_usa_los_colores_de_setesa():
    config = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    tema = config["theme"]
    assert tema["primaryColor"].lower() == estilos.AZUL.lower()
    assert tema["base"] == "light" and tema["backgroundColor"].upper() == "#FFFFFF"
    assert config["theme"]["sidebar"]["backgroundColor"].lower() == estilos.AZUL.lower()
    assert config["client"]["toolbarMode"] == "minimal"


def test_los_estilos_se_inyectan_con_los_colores_de_la_marca(st_falso):
    estilos.aplicar_estilos()
    css = st_falso.html[0]
    assert css.startswith("<style>") and estilos.AZUL in css and estilos.CELESTE in css
    assert css.count("{") == css.count("}")  # llaves balanceadas


def test_un_fallo_en_los_estilos_no_detiene_la_aplicacion(monkeypatch):
    monkeypatch.setattr(estilos, "st", _Streamlit(falla=True))
    estilos.aplicar_estilos()  # no debe lanzar


def test_el_encabezado_escapa_el_contenido(st_falso):
    estilos.encabezado("<script>alert(1)</script>", "<b>sub</b>")
    html = st_falso.html[0]
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<b>" not in html


def test_la_tarjeta_del_usuario_escapa_el_nombre(st_falso):
    estilos.perfil_lateral('<img src=x onerror="alert(1)">', "Consultor")
    html = st_falso.html[0]
    assert "<img" not in html and "&lt;img" in html
    assert "Perfil de Usuario" in html and "Consultor" in html
    assert st_falso.imagenes  # logo de SETESA


def test_las_tablas_resaltan_estados_y_resoluciones():
    df = pd.DataFrame({
        "estado_workflow": ["Finalizada", "Pendiente de Firma Coordinador"],
        "resolucion": ["Denegada", "—"],
        "otra": [1, 2],
    })
    html = estilos.colorear_estados(df).to_html()
    assert "#FBE4E4" in html      # denegada
    assert "#E3F4E8" in html      # finalizada
    assert "#FFF4D6" in html      # pendiente del banco


def test_una_tabla_sin_esas_columnas_se_devuelve_igual():
    df = pd.DataFrame({"a": [1]})
    assert estilos.colorear_estados(df) is df
