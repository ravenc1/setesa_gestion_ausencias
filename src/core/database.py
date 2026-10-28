# Manejador de la conexión a PostgreSQL.
#
# `get_connection` se usa para las escrituras transaccionales (psycopg2) y
# `get_engine` para las lecturas con pandas (SQLAlchemy), lo que elimina la
# advertencia de pandas y centraliza el pool de conexiones (H-21).

from functools import lru_cache

import psycopg2
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

from src.core.config import obtener_variable
from src.core.logging_config import obtener_logger

load_dotenv()

logger = obtener_logger("setesa.database")


def _url_sqlalchemy(url):
    """Adapta la URL de psycopg2 al dialecto que espera SQLAlchemy."""
    if url.startswith("postgresql+psycopg2://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def get_connection():
    try:
        DATABASE_URL = obtener_variable("DATABASE_URL")
        if not DATABASE_URL:
            st.error("Falta DATABASE_URL en .env o en los secrets de Streamlit")
            return None

        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.exception("Error al conectar a PostgreSQL")
        st.error(f"Error crítico en la capa de datos: {e}")
        return None


@lru_cache(maxsize=1)
def get_engine():
    """Devuelve el motor SQLAlchemy (o None si falta DATABASE_URL)."""
    url = obtener_variable("DATABASE_URL")
    if not url:
        return None
    return create_engine(_url_sqlalchemy(url), pool_pre_ping=True)
