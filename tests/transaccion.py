# Ayudante de pruebas: ejecuta código de la aplicación contra la base real
# dentro de UNA transacción que se revierte al final, sin dejar nada guardado.

import os
from contextlib import contextmanager

import psycopg2


class ConexionTransaccional:
    """Envuelve una conexión real: commit y close no hacen nada."""

    def __init__(self, conexion):
        self._conexion = conexion

    def cursor(self):
        return self._conexion.cursor()

    def commit(self):
        pass

    def close(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@contextmanager
def transaccion_revertida(monkeypatch, *modulos, ddl=()):
    """Reemplaza ``get_connection`` de ``modulos`` por la conexión revertible.

    Ejecuta ``ddl`` (sentencias) dentro de la transacción antes de ceder el
    cursor. Todo se revierte al salir.
    """
    real = psycopg2.connect(os.environ["DATABASE_URL"])
    cursor = real.cursor()
    try:
        for sentencia in ddl:
            cursor.execute(sentencia)
        proxy = ConexionTransaccional(real)
        for modulo in modulos:
            monkeypatch.setattr(modulo, "get_connection", lambda proxy=proxy: proxy)
        yield cursor
    finally:
        real.rollback()
        cursor.close()
        real.close()
