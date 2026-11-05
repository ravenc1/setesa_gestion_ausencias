# Panel de Gerencia para reasignar expedientes a otro Coordinador GTC (Fase 12).

import streamlit as st

from src.core.reasignacion import (
    ReasignacionError,
    listar_expedientes_reasignables,
    reasignar_coordinador,
)
from src.core.security import rol_autorizado
from src.core.usuarios import listar_coordinadores


def mostrar_panel_reasignacion():
    if not rol_autorizado(["Administrador", "IT"]):
        st.error("Acceso denegado: esta sección es exclusiva de Gerencia e IT.")
        return

    st.markdown("### 🔁 Reasignar Coordinador GTC")
    flash = st.session_state.pop("flash_reasignacion", None)
    if flash:
        st.success(flash)
    st.info(
        "Si un Coordinador GTC deja de estar asignado en el banco, IT lo da "
        "de baja y reasigna aquí sus expedientes. Si llega un coordinador "
        "nuevo, IT primero lo registra en «Crear usuario». Si un Coordinador "
        "GTC se da de baja o no puede atender, sus "
        "expedientes pendientes de visto bueno pueden pasar a otro "
        "coordinador vigente. El cambio queda en el historial del expediente."
    )

    df = listar_expedientes_reasignables()
    if df.empty:
        st.success("No hay expedientes esperando el visto bueno del banco.")
        return

    huerfanos = int((~df["coordinador_vigente"]).sum())
    if huerfanos:
        st.warning(
            f"⚠️ {huerfanos} expediente(s) están asignados a un coordinador "
            "que ya no está vigente. Reasígnelos para que puedan avanzar."
        )

    vista = df.assign(
        coordinador_vigente=df["coordinador_vigente"].map(
            {True: "Sí", False: "No"}
        )
    ).drop(columns=["id_coordinador"])
    st.dataframe(vista, hide_index=True, width="stretch")

    coordinadores = listar_coordinadores()
    if coordinadores.empty:
        st.error(
            "No hay Coordinadores GTC vigentes. Solicite a IT que registre uno."
        )
        return
    nombres = dict(
        zip(
            coordinadores["id_usuario"].astype(int),
            coordinadores["nombre_completo"],
        )
    )

    st.write("---")
    with st.form("form_reasignacion"):
        id_solicitud = st.selectbox(
            "Expediente a reasignar",
            df["id_solicitud"].astype(int).tolist(),
            format_func=lambda i: (
                f"#{i} · "
                + df.loc[df["id_solicitud"] == i, "consultor"].iloc[0]
                + " · actual: "
                + df.loc[df["id_solicitud"] == i, "coordinador"].iloc[0]
            ),
        )
        id_nuevo = st.selectbox(
            "Nuevo Coordinador GTC", list(nombres), format_func=nombres.get
        )
        motivo = st.text_area("Motivo de la reasignación", height=80)
        enviar = st.form_submit_button("Reasignar expediente", type="primary")

    if enviar:
        try:
            resultado = reasignar_coordinador(
                int(id_solicitud),
                int(id_nuevo),
                st.session_state["id_usuario"],
                motivo,
            )
        except ReasignacionError as e:
            st.error(f"❌ {e}")
        except Exception as e:
            st.error(f"No se pudo reasignar el expediente: {e}")
        else:
            st.session_state["flash_reasignacion"] = (
                f"Expediente #{id_solicitud} reasignado a {resultado['nuevo']}. "
                f"Recordatorios trasladados: {resultado['recordatorios']}."
            )
            st.rerun()
