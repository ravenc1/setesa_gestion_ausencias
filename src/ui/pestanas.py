# Pestañas que solo ejecutan el contenido de la abierta (Fase 24).
#
# Con st.tabs normal, Streamlit ejecuta TODAS las pestañas en cada clic (y cada
# una consulta la base). Con ``on_change="rerun"`` solo corre la pestaña
# visible; al cambiar de pestaña se vuelve a ejecutar la pantalla.

import streamlit as st


def pestanas(nombres, key):
    return st.tabs(nombres, key=key, on_change="rerun")


def abierta(pestana):
    """True si la pestaña está visible (o si no se puede saber)."""
    return getattr(pestana, "open", True) is not False
