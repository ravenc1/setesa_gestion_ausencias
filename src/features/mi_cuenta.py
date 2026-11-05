# Pantalla para cambiar la contraseña (Fase 24).

import streamlit as st

from src.core.cuenta import PasswordError, cambiar_password


def mostrar_cambio_password(obligatorio=False):
    st.markdown("### 🔑 " + ("Cambio de contraseña obligatorio" if obligatorio else "Mi contraseña"))
    flash = st.session_state.pop("flash_password", None)
    if flash:
        st.success(flash)

    if obligatorio:
        st.warning(
            "IT le entregó una contraseña **temporal**. Por seguridad, elija una "
            "contraseña propia para continuar."
        )
    else:
        st.info(
            "Cambie su contraseña cuando lo necesite. Si la olvida, solo IT "
            "puede restablecerla y entregarle una temporal."
        )

    with st.form("form_cambio_password", clear_on_submit=True):
        actual = st.text_input(
            "Contraseña actual" + (" (la temporal que le dio IT)" if obligatorio else ""),
            type="password",
        )
        nueva = st.text_input(
            "Contraseña nueva",
            type="password",
            help="Mínimo 8 caracteres, con al menos una letra y un número.",
        )
        confirmar = st.text_input("Confirmar contraseña nueva", type="password")
        guardar = st.form_submit_button("🔑 Cambiar contraseña", type="primary")

    if guardar:
        try:
            cambiar_password(st.session_state["id_usuario"], actual, nueva, confirmar)
        except PasswordError as e:
            st.error(f"❌ {e}")
        except Exception as e:
            st.error(f"No se pudo cambiar la contraseña: {e}")
        else:
            st.session_state["debe_cambiar_password"] = False
            st.session_state["flash_password"] = "Contraseña actualizada correctamente."
            st.rerun()
