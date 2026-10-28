# Rutas centralizadas del proyecto y acceso unificado a la configuración.

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = PROJECT_ROOT / "storage"
PDF_DIR = STORAGE_DIR / "pdf"
FIRMAS_DIR = STORAGE_DIR / "firmas"
LOG_DIR = STORAGE_DIR / "logs"


def obtener_variable(nombre):
    """Lee una variable desde el entorno o desde los secrets de Streamlit.

    `.env` cubre el desarrollo local y los servidores con variables de entorno;
    `st.secrets` cubre Streamlit Community Cloud, que no inyecta secretos como
    variables de entorno. Si no existe ninguna de las dos fuentes, devuelve None.
    """
    valor = os.getenv(nombre)
    if valor:
        return valor

    try:
        import streamlit as st

        return st.secrets.get(nombre)
    except Exception:
        return None


def ensure_dirs():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    FIRMAS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
