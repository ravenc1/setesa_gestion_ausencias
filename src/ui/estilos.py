# Identidad visual de SETESA: azul y blanco (Fase 23).
#
# El tema base (colores, bordes, tablas, barra lateral) vive en
# .streamlit/config.toml. Aquí van los retoques que el tema no cubre:
# encabezados, tarjetas de indicadores, formularios, pestañas y la tarjeta del
# usuario en la barra lateral.
#
# Los estilos usan los selectores data-testid de Streamlit (versión fijada en
# requirements.txt). Si una actualización cambiara alguno, solo se pierde el
# adorno de ese elemento: la aplicación sigue funcionando.

import html
from pathlib import Path

import streamlit as st

from src.core.config import PROJECT_ROOT

LOGO = PROJECT_ROOT / "assets" / "logo_setesa.png"
ICONO = PROJECT_ROOT / "assets" / "icono_setesa.png"

AZUL = "#203868"
CELESTE = "#68B0D8"
CLARO = "#EAF2FA"
BORDE = "#C9D9EC"

CSS = f"""
:root {{
  --setesa-azul: {AZUL};
  --setesa-celeste: {CELESTE};
  --setesa-claro: {CLARO};
  --setesa-borde: {BORDE};
}}

/* Estructura */
[data-testid="stAppViewContainer"] > .main, [data-testid="stMain"] {{
  background: linear-gradient(180deg, #F1F6FC 0%, #FFFFFF 320px);
}}
.block-container {{ padding-top: 2.2rem; max-width: 1280px; }}
[data-testid="stHeader"] {{ background: transparent; }}
footer {{ visibility: hidden; }}
h1, h2, h3, h4, h5 {{ color: var(--setesa-azul); letter-spacing: -0.01em; }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4 {{ color: #FFFFFF; }}
hr {{ border-color: var(--setesa-borde); }}

/* Encabezado de cada panel */
.setesa-hero {{
  background: linear-gradient(120deg, {AZUL} 0%, #2B5CA8 62%, {CELESTE} 130%);
  color: #FFFFFF; padding: 1.35rem 1.8rem; border-radius: 16px;
  margin: 0 0 1.4rem 0; box-shadow: 0 8px 22px rgba(32, 56, 104, .20);
}}
.setesa-hero .titulo {{ font-size: 1.65rem; font-weight: 700; line-height: 1.2; }}
.setesa-hero .subtitulo {{ color: #DCEBFA; font-size: .95rem; margin-top: .3rem; }}

/* Indicadores */
[data-testid="stMetric"] {{
  background: #FFFFFF; border: 1px solid var(--setesa-borde);
  border-left: 5px solid var(--setesa-azul); border-radius: 12px;
  padding: .85rem 1rem; box-shadow: 0 2px 10px rgba(32, 56, 104, .07);
}}
[data-testid="stMetricLabel"] {{ color: #4A5F8F; font-weight: 600; }}
[data-testid="stMetricValue"] {{ color: var(--setesa-azul); font-weight: 700; }}

/* Pestañas */
.stTabs [data-baseweb="tab-list"] {{
  gap: .3rem; border-bottom: 2px solid var(--setesa-borde);
}}
.stTabs [data-baseweb="tab"] {{
  font-weight: 600; padding: .6rem 1.05rem; border-radius: 10px 10px 0 0;
}}
.stTabs [aria-selected="true"] {{
  color: var(--setesa-azul); background: var(--setesa-claro);
}}

/* Formularios, bloques y avisos */
[data-testid="stForm"] {{
  background: #FFFFFF; border: 1px solid var(--setesa-borde); border-radius: 14px;
  padding: 1.3rem; box-shadow: 0 4px 16px rgba(32, 56, 104, .07);
}}
[data-testid="stExpander"] {{
  border: 1px solid var(--setesa-borde); border-radius: 12px; background: #FFFFFF;
}}
[data-testid="stAlert"] {{ border-radius: 12px; }}
[data-testid="stDataFrame"] {{
  border-radius: 12px; overflow: hidden;
  box-shadow: 0 2px 10px rgba(32, 56, 104, .07);
}}
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div {{ border-radius: 10px; }}

/* Botones */
.stButton > button, .stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button {{
  font-weight: 600; border-radius: 10px; transition: all .15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover {{
  transform: translateY(-1px); box-shadow: 0 6px 14px rgba(32, 56, 104, .18);
}}
.stButton > button[kind="secondary"], .stDownloadButton > button[kind="secondary"],
[data-testid="stFormSubmitButton"] > button[kind="secondary"] {{
  border: 1.5px solid var(--setesa-azul); color: var(--setesa-azul);
}}

/* Barra lateral */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, {AZUL} 0%, #172A50 100%);
}}
[data-testid="stSidebar"] [data-testid="stImage"] img {{
  background: #FFFFFF; border-radius: 12px; padding: .55rem .8rem;
}}
[data-testid="stSidebar"] .stButton > button {{
  background: transparent; color: #FFFFFF; border: 1.5px solid rgba(255, 255, 255, .55);
}}
[data-testid="stSidebar"] .stButton > button:hover {{
  background: rgba(255, 255, 255, .12); border-color: #FFFFFF;
}}
.setesa-perfil {{
  background: rgba(255, 255, 255, .09); border: 1px solid rgba(255, 255, 255, .18);
  border-radius: 14px; padding: .9rem 1rem; margin: .6rem 0 .4rem 0;
}}
.setesa-perfil .etiqueta {{
  font-size: .7rem; letter-spacing: .08em; text-transform: uppercase; color: #BFD9F0;
}}
.setesa-perfil .nombre {{ font-weight: 700; font-size: 1.02rem; margin: .15rem 0 .5rem; }}
.setesa-perfil .rol {{
  display: inline-block; background: {CELESTE}; color: {AZUL}; font-weight: 700;
  font-size: .78rem; padding: .18rem .7rem; border-radius: 999px;
}}

/* Inicio de sesión */
.setesa-login-titulo {{
  text-align: center; color: var(--setesa-azul); font-size: 1.5rem;
  font-weight: 700; margin: .4rem 0 .1rem;
}}
.setesa-login-subtitulo {{ text-align: center; color: #5B6F94; margin-bottom: 1.2rem; }}

/* Pie de página */
.setesa-pie {{
  text-align: center; color: #6B7FA3; font-size: .8rem; margin-top: 2.6rem;
  padding-top: 1rem; border-top: 1px solid var(--setesa-borde);
}}
"""


def aplicar_estilos():
    """Inyecta los estilos de SETESA. Un fallo nunca detiene la aplicación."""
    try:
        st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    except Exception:
        pass


def encabezado(titulo, subtitulo=""):
    """Banner azul de cada panel. Los textos se escapan (vienen de la base)."""
    sub = (
        f'<div class="subtitulo">{html.escape(subtitulo)}</div>' if subtitulo else ""
    )
    st.markdown(
        f'<div class="setesa-hero"><div class="titulo">{html.escape(titulo)}</div>'
        f"{sub}</div>",
        unsafe_allow_html=True,
    )


def perfil_lateral(nombre, rol):
    """Logo y tarjeta del usuario en la barra lateral."""
    if LOGO.exists():
        st.sidebar.image(str(LOGO), width="stretch")
    st.sidebar.markdown(
        '<div class="setesa-perfil">'
        '<div class="etiqueta">Perfil de Usuario</div>'
        f'<div class="nombre">{html.escape(str(nombre))}</div>'
        f'<span class="rol">{html.escape(str(rol))}</span></div>',
        unsafe_allow_html=True,
    )


def pie_de_pagina():
    st.markdown(
        '<div class="setesa-pie">SETESA · Plataforma de Gestión de Ausencias y '
        "Vigencia</div>",
        unsafe_allow_html=True,
    )


# Colores de los estados del flujo y de las resoluciones (tablas del dashboard).
_COLORES_ESTADO = {
    "Ingresada": ("#EAF2FA", "#203868"),
    "Pendiente de Firma Coordinador": ("#FFF4D6", "#7A5A00"),
    "Pendiente de Aprobación Gerencia": ("#DCEBFA", "#203868"),
    "Finalizada": ("#E3F4E8", "#14532D"),
    "Aprobada": ("#E3F4E8", "#14532D"),
    "Denegada": ("#FBE4E4", "#7F1D1D"),
}


def _color(valor):
    fondo, texto = _COLORES_ESTADO.get(valor, (None, None))
    return f"background-color: {fondo}; color: {texto}; font-weight: 600" if fondo else ""


def colorear_estados(df, columnas=("estado_workflow", "resolucion")):
    """Tabla con los estados y resoluciones resaltados; sin Styler si falla."""
    presentes = [c for c in columnas if c in df.columns]
    if not presentes:
        return df
    try:
        return df.style.map(_color, subset=presentes)
    except Exception:
        return df
