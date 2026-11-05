# Manejador de la conexión a PostgreSQL.
#
# `get_connection` se usa para las escrituras transaccionales (psycopg2) y
# `get_engine` para las lecturas con pandas (SQLAlchemy), lo que elimina la
# advertencia de pandas y centraliza el pool de conexiones (H-21).

import threading
import time
from functools import lru_cache

import psycopg2
from psycopg2 import pool
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


# Fase 24: reserva de conexiones. Abrir una conexión a Supabase cuesta cientos
# de milisegundos (varios viajes de red); se reutilizan en lugar de abrir una
# por consulta. ``conn.close()`` devuelve la conexión a la reserva.
MAX_CONEXIONES = 10
SEGUNDOS_ANTES_DE_VALIDAR = 20

_reserva = None
_candado = threading.Lock()
_ultimo_uso = {}


class ConexionDeReserva:
    """Envuelve una conexión de la reserva: ``close()`` la devuelve, no la cierra."""

    def __init__(self, reserva, conexion):
        object.__setattr__(self, "_reserva", reserva)
        object.__setattr__(self, "_conexion", conexion)
        object.__setattr__(self, "_devuelta", False)

    def __getattr__(self, nombre):
        return getattr(self._conexion, nombre)

    def __setattr__(self, nombre, valor):
        setattr(self._conexion, nombre, valor)

    def __enter__(self):
        self._conexion.__enter__()
        return self

    def __exit__(self, *excepcion):
        return self._conexion.__exit__(*excepcion)

    def close(self):
        if self._devuelta:
            return
        object.__setattr__(self, "_devuelta", True)
        conexion = self._conexion
        try:
            if not conexion.closed:
                conexion.rollback()  # nunca se devuelve con una transacción abierta
        except Exception:
            pass
        _ultimo_uso[id(conexion)] = time.monotonic()
        if self._reserva is None:  # conexión de emergencia, fuera de la reserva
            conexion.close()
            return
        try:
            self._reserva.putconn(conexion, close=bool(conexion.closed))
        except Exception:
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _conexion_valida(conexion):
    """Una conexión inactiva mucho tiempo puede haber sido cerrada por el servidor."""
    if conexion.closed:
        return False
    if time.monotonic() - _ultimo_uso.get(id(conexion), 0) < SEGUNDOS_ANTES_DE_VALIDAR:
        return True
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT 1")
        conexion.rollback()
        return True
    except Exception:
        return False


def _obtener_reserva(url):
    global _reserva
    with _candado:
        if _reserva is None:
            _reserva = pool.ThreadedConnectionPool(
                1, MAX_CONEXIONES, url,
                connect_timeout=15, keepalives=1, keepalives_idle=30,
                keepalives_interval=10, keepalives_count=3,
            )
        return _reserva


def get_connection():
    try:
        DATABASE_URL = obtener_variable("DATABASE_URL")
        if not DATABASE_URL:
            st.error("Falta DATABASE_URL en .env o en los secrets de Streamlit")
            return None

        reserva = _obtener_reserva(DATABASE_URL)
        for _ in range(3):
            try:
                conexion = reserva.getconn()
            except pool.PoolError:
                # Reserva agotada: conexión propia para no bloquear al usuario.
                logger.warning("Reserva de conexiones agotada; se abre una temporal.")
                return ConexionDeReserva(None, psycopg2.connect(DATABASE_URL))
            if _conexion_valida(conexion):
                return ConexionDeReserva(reserva, conexion)
            reserva.putconn(conexion, close=True)
        return ConexionDeReserva(None, psycopg2.connect(DATABASE_URL))
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
