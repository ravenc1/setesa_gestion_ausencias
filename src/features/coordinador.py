# Panel exclusivo donde el jefe inmediato GTC ve las solicitudes del consultor.

import streamlit as st
import pandas as pd

from src.core.database import get_connection
from src.core.workflow import (
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)
from src.core.security import rol_autorizado
from src.core.solicitudes import (
    FirmaRequerida,
    TransicionInvalida,
    cambiar_estado,
    obtener_historial,
)
from src.services.documentos import generar_pdf_solicitud
from src.services.utils_firma import canvas_to_base64


def obtener_solicitudes_pendientes():
    """Recupera las solicitudes que esperan la firma del Coordinador GTC."""
    conn = get_connection()
    if conn:
        try:
            query = """
                SELECT s.id_solicitud, u.nombre_completo, s.tipo_ausencia,
                       s.fecha_inicio, s.fecha_fin, s.fecha_creacion
                FROM solicitud s
                JOIN usuario u ON s.id_usuario = u.id_usuario
                WHERE s.estado_workflow = %s
                ORDER BY s.fecha_creacion ASC
            """
            df = pd.read_sql_query(
                query, conn, params=(ESTADO_PENDIENTE_FIRMA_COORDINADOR,)
            )
            conn.close()
            return df
        except Exception as e:
            st.error(f"Error al obtener datos: {e}")
            return pd.DataFrame()
    return pd.DataFrame()


def firmar_aprobacion_banco(id_solicitud, id_usuario, firma_b64):
    """Aplica la transición validada y guarda la firma del Coordinador GTC."""
    try:
        cambiar_estado(
            id_solicitud,
            ESTADO_PENDIENTE_APROBACION_GERENCIA,
            id_usuario,
            "Visto bueno del Coordinador GTC.",
            firma_b64=firma_b64,
        )
        return True
    except FirmaRequerida as e:
        st.error(f"Debe firmar el expediente: {e}")
    except TransicionInvalida as e:
        st.error(f"No se puede aprobar: {e}")
    except Exception as e:
        st.error(f"Error al aplicar la aprobación: {e}")
    return False


def mostrar_panel_coordinador():
    if not rol_autorizado(["Coordinador GTC"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Coordinador GTC.")
        return

    st.markdown("### 🏦 Portal de Aprobaciones - GTC")
    flash = st.session_state.pop("flash_coordinador", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.info(
        "Módulo de revisión para Coordinadores. Las solicitudes aprobadas aquí "
        "serán enviadas a la Gerencia de SETESA para su validación final."
    )

    df_pendientes = obtener_solicitudes_pendientes()

    if df_pendientes.empty:
        st.success("Su bandeja está limpia. No hay solicitudes pendientes de revisión.")
        return

    st.write("**Bandeja de Entrada: Solicitudes de Consultores SETESA**")
    st.dataframe(df_pendientes, width="stretch", hide_index=True)

    st.write("---")
    st.markdown("#### 🖋️ Autorización del Coordinador GTC")

    id_seleccionado = st.selectbox(
        "Seleccione el ID del expediente a aprobar:",
        df_pendientes["id_solicitud"].tolist(),
    )

    from streamlit_drawable_canvas import st_canvas  # import perezoso: requiere el runtime

    st.info("💡 Dibuje su firma en el recuadro; quedará estampada en el PDF oficial.")
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="rgba(0, 0, 0, 0)",
        height=100,
        width=300,
        drawing_mode="freedraw",
        key=f"canvas_coordinador_{id_seleccionado}",
        return_image_data=True,
    )

    btn_firmar = st.button(
        "Otorgar Visto Bueno y enviar a Gerencia",
        type="primary",
    )

    if btn_firmar and id_seleccionado:
        firma_base64 = None
        if canvas_result.image_data is not None:
            firma_base64 = canvas_to_base64(canvas_result.image_data)

        if not firma_base64:
            st.error("❌ Debe dibujar su firma antes de aprobar el expediente.")
        elif firmar_aprobacion_banco(
            id_seleccionado, st.session_state["id_usuario"], firma_base64
        ):
            try:
                ruta = generar_pdf_solicitud(id_seleccionado)
                st.session_state["flash_coordinador"] = (
                    "success",
                    f"¡Expediente {id_seleccionado} aprobado y firmado! "
                    f"PDF actualizado en {ruta}.",
                )
            except Exception as e:
                st.session_state["flash_coordinador"] = (
                    "warning",
                    f"El expediente {id_seleccionado} fue aprobado, pero no se "
                    f"pudo generar el PDF: {e}",
                )
            st.rerun()

    with st.expander(f"🕓 Historial de estados del expediente #{id_seleccionado}"):
        df_movimientos = obtener_historial(id_seleccionado)
        if df_movimientos.empty:
            st.info("Sin movimientos registrados.")
        else:
            st.dataframe(df_movimientos, hide_index=True, width="stretch")
