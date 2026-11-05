# Fase 24: guardado temporal de lecturas (rendimiento).
#
# Streamlit vuelve a ejecutar la pantalla completa en cada clic, y cada lectura
# es un viaje a la base de datos. Las lecturas que casi no cambian se guardan
# unos segundos en memoria con ``@lectura(ttl)``. Toda función que escribe se
# marca con ``@escritura``: al terminar borra TODO lo guardado, así el propio
# usuario nunca ve datos viejos tras una acción suya.
#
# Reglas:
#   - Las validaciones de negocio (saldo de vacaciones al registrar, permisos,
#     transiciones) NO usan estas lecturas: leen directo de la base.
#   - Los cambios hechos fuera de la aplicación (pg_cron, tareas) se ven al
#     vencer el TTL (segundos).
#   - Con SETESA_SIN_CACHE=1 todo se desactiva (las pruebas lo usan).

import functools
import os

import streamlit as st


def _activo():
    return not os.getenv("SETESA_SIN_CACHE")


def lectura(ttl=30):
    """Guarda el resultado de una lectura ``ttl`` segundos (por argumentos).

    El interruptor SETESA_SIN_CACHE se revisa en cada llamada, así las pruebas
    pueden activar o desactivar el guardado.
    """

    def decorador(funcion):
        guardada = st.cache_data(ttl=ttl, show_spinner=False)(funcion)

        @functools.wraps(funcion)
        def envoltura(*args, **kwargs):
            return (guardada if _activo() else funcion)(*args, **kwargs)

        return envoltura

    return decorador


def invalidar():
    """Borra todo lo guardado; nunca falla (también funciona fuera de Streamlit)."""
    try:
        st.cache_data.clear()
    except Exception:
        pass


def escritura(funcion):
    """Marca una función que modifica datos: invalida las lecturas al terminar."""

    @functools.wraps(funcion)
    def envoltura(*args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        finally:
            invalidar()

    return envoltura
