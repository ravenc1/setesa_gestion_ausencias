# Panel de Gerencia para mantener el catálogo de motivos de ausencia (Fase 21).

import streamlit as st

from src.core.motivos import (
    MotivoError,
    NOMBRE_MAX,
    cambiar_estado_motivo,
    crear_motivo,
    listar_motivos,
)
from src.core.security import rol_autorizado


def mostrar_panel_motivos():
    if not rol_autorizado(["Administrador"]):
        st.error("Acceso denegado: esta sección es exclusiva de Gerencia.")
        return

    st.markdown("### 🏷️ Catálogo de motivos de ausencia")
    flash = st.session_state.pop("flash_motivos", None)
    if flash:
        st.success(flash)
    st.info(
        "Lista cerrada de motivos que ofrece el formulario de ausencia. Los 22 "
        "motivos de la plantilla oficial se pueden desactivar, no renombrar. "
        "Un motivo nuevo no tiene casilla en la hoja oficial: en el PDF se "
        "marca «OTROS» y se escribe su nombre. Desactivar un motivo no afecta "
        "a las solicitudes ya registradas."
    )

    df = listar_motivos()
    if df.empty:
        st.warning("El catálogo está vacío; ejecute la migración de la Fase 21.")
        return

    vista = df.assign(
        activo=df["activo"].map({True: "Sí", False: "No"}),
        origen=df["en_plantilla"].map({True: "Plantilla oficial", False: "Agregado"}),
        regla_propia=df["protegido"].map({True: "Sí", False: ""}),
    )[["nombre", "activo", "origen", "regla_propia"]]
    st.dataframe(
        vista.rename(columns={
            "nombre": "Motivo", "activo": "Activo",
            "origen": "Origen", "regla_propia": "Regla propia",
        }),
        hide_index=True,
        width="stretch",
    )

    st.write("---")
    st.markdown("#### ➕ Agregar un motivo")
    with st.form("form_nuevo_motivo", clear_on_submit=True):
        nombre = st.text_input(
            "Nombre del motivo", max_chars=NOMBRE_MAX,
            help="Se guarda en mayúsculas.",
        )
        agregar = st.form_submit_button("Agregar motivo", type="primary")
    if agregar:
        try:
            creado = crear_motivo(st.session_state["id_usuario"], nombre)
        except MotivoError as e:
            st.error(f"❌ {e}")
        else:
            st.session_state["flash_motivos"] = f"Motivo «{creado}» agregado."
            st.rerun()

    st.write("---")
    st.markdown("#### 🔄 Activar o desactivar")
    etiquetas = {
        int(f.id_motivo): f"{f.nombre} · {'activo' if f.activo else 'inactivo'}"
        for f in df.itertuples()
    }
    id_motivo = st.selectbox("Motivo", list(etiquetas), format_func=etiquetas.get)
    fila = df[df["id_motivo"] == id_motivo].iloc[0]
    if fila["protegido"]:
        st.caption(
            "Este motivo tiene una regla propia (saldo de vacaciones o "
            "constancia del IGSS) y no se puede desactivar."
        )
    nuevo_estado = not bool(fila["activo"])
    if st.button(
        "✅ Activar motivo" if nuevo_estado else "🚫 Desactivar motivo",
        disabled=bool(fila["protegido"]) and not nuevo_estado,
    ):
        try:
            cambiar_estado_motivo(
                st.session_state["id_usuario"], int(id_motivo), nuevo_estado
            )
        except MotivoError as e:
            st.error(f"❌ {e}")
        else:
            st.session_state["flash_motivos"] = (
                f"Motivo «{fila['nombre']}» "
                f"{'activado' if nuevo_estado else 'desactivado'}."
            )
            st.rerun()
