# Bandeja de avisos dentro del sistema (Fase 18).

import streamlit as st

from src.core.notificaciones import (
    contar_no_leidas,
    enlace_al_consultor,
    listar_notificaciones,
    marcar_leidas,
)


def etiqueta_menu(id_usuario):
    """Texto del menú con la cantidad de avisos sin leer."""
    try:
        pendientes = contar_no_leidas(id_usuario)
    except Exception:
        pendientes = 0
    return f"🔔 Avisos ({pendientes})" if pendientes else "🔔 Avisos"


def mostrar_notificaciones():
    id_usuario = st.session_state.get("id_usuario")
    es_contabilidad = st.session_state.get("rol") == "Contabilidad"

    st.markdown("### 🔔 Avisos")
    st.info(
        "Aquí aparecen los expedientes que fueron finalizados (aprobados o "
        "denegados)."
        + (
            " Puede escribir al consultor con el enlace de cada aviso."
            if es_contabilidad
            else ""
        )
    )

    df = listar_notificaciones(id_usuario)
    if df.empty:
        st.success("No tiene avisos.")
        return

    sin_leer = df[~df["leida"]]
    if not sin_leer.empty and st.button("✅ Marcar todos como leídos"):
        marcar_leidas(id_usuario)
        st.rerun()

    for fila in df.to_dict("records"):
        marca = "🆕 " if not fila["leida"] else ""
        st.markdown(f"{marca}**{fila['fecha']:%d/%m/%Y %H:%M}** — {fila['mensaje']}")
        if es_contabilidad and fila["correo_consultor"]:
            st.markdown(f"&nbsp;&nbsp;[✉️ Escribir a {fila['consultor']}]({enlace_al_consultor(fila)})")
