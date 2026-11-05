# Panel exclusivo donde el jefe inmediato GTC ve las solicitudes del consultor.

import streamlit as st
import pandas as pd

from src.core.cache import lectura
from src.core.database import get_engine
from src.core.logging_config import obtener_logger
from src.core.workflow import (
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)
from src.core.security import rol_autorizado
from src.core.recordatorios import obtener_recordatorios_pendientes
from src.core.solicitudes import (
    CoordinadorNoAsignado,
    FirmaRequerida,
    MotivoRequerido,
    TransicionInvalida,
    cambiar_estado,
    denegar_solicitud,
    obtener_historial,
)
from src.services.documentos import generar_pdf_solicitud
from src.services.utils_firma import canvas_to_base64

logger = obtener_logger("setesa.coordinador")


@lectura(ttl=15)
def _leer_pendientes(id_coordinador):
    """Lectura guardada unos segundos; si falla, lanza (los errores no se guardan)."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    query = """
        SELECT s.id_solicitud, u.nombre_completo, s.tipo_ausencia,
               s.fecha_inicio, s.fecha_fin, s.fecha_creacion
        FROM solicitud s
        JOIN usuario u ON s.id_usuario = u.id_usuario
        WHERE s.estado_workflow = %s
          AND s.id_coordinador = %s
        ORDER BY s.fecha_creacion ASC
    """
    return pd.read_sql_query(
        query,
        engine,
        params=(ESTADO_PENDIENTE_FIRMA_COORDINADOR, id_coordinador),
    )


def obtener_solicitudes_pendientes(id_coordinador):
    """Solicitudes que esperan la firma de ESTE Coordinador GTC.

    Tabla 9 de la tesis: la bandeja muestra solo las solicitudes asignadas a
    su equipo, es decir, las que el consultor dirigió a este jefe inmediato.
    """
    try:
        return _leer_pendientes(id_coordinador)
    except Exception as e:
        logger.exception("Error al obtener las solicitudes pendientes")
        st.error(f"Error al obtener datos: {e}")
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
    except CoordinadorNoAsignado as e:
        st.error(f"No puede aprobar: {e}")
    except FirmaRequerida as e:
        st.error(f"Debe firmar el expediente: {e}")
    except TransicionInvalida as e:
        st.error(f"No se puede aprobar: {e}")
    except Exception as e:
        st.error(f"Error al aplicar la aprobación: {e}")
    return False


def denegar_permiso_banco(id_solicitud, id_usuario, motivo, firma_b64):
    """El banco no otorga el permiso: deniega y cierra el expediente."""
    try:
        denegar_solicitud(id_solicitud, id_usuario, motivo, firma_b64)
        return True
    except MotivoRequerido as e:
        st.error(f"❌ {e}")
    except CoordinadorNoAsignado as e:
        st.error(f"No puede denegar: {e}")
    except FirmaRequerida as e:
        st.error(f"Debe firmar el expediente: {e}")
    except TransicionInvalida as e:
        st.error(f"No se puede denegar: {e}")
    except Exception as e:
        st.error(f"Error al denegar: {e}")
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
        "serán enviadas a la Gerencia de SETESA para su validación final. Si "
        "el banco no otorga el permiso, deniéguela indicando el motivo."
    )

    df_pendientes = obtener_solicitudes_pendientes(st.session_state.get("id_usuario"))

    # R-11: recordatorios que los consultores enviaron a este coordinador.
    df_recordatorios = obtener_recordatorios_pendientes(
        st.session_state.get("id_usuario")
    )
    if not df_recordatorios.empty:
        st.warning(
            f"🔔 Tiene {len(df_recordatorios)} recordatorio(s) de consultores "
            "esperando su visto bueno."
        )
        with st.expander("🔔 Recordatorios recibidos", expanded=True):
            st.dataframe(df_recordatorios, hide_index=True, width="stretch")

    if df_pendientes.empty:
        st.success("Su bandeja está limpia. No hay solicitudes pendientes de revisión.")
        return

    st.write("**Bandeja de Entrada: Solicitudes de Consultores SETESA**")
    st.dataframe(df_pendientes, width="stretch", hide_index=True)

    st.write("---")
    st.markdown("#### 🖋️ Autorización del Coordinador GTC")

    id_seleccionado = st.selectbox(
        "Seleccione el ID del expediente a revisar:",
        df_pendientes["id_solicitud"].tolist(),
    )

    # Fase 16: el banco aprueba o deniega.
    decision = st.radio(
        "Decisión del banco",
        ["Otorgar visto bueno", "Denegar"],
        horizontal=True,
        key=f"decision_coordinador_{id_seleccionado}",
    )
    denegar = decision == "Denegar"
    motivo = ""
    if denegar:
        motivo = st.text_area(
            "Motivo de la denegación (obligatorio; lo verán el consultor y "
            "SETESA)",
            key=f"motivo_coordinador_{id_seleccionado}",
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
        "⛔ Denegar y Firmar" if denegar else "Otorgar Visto Bueno y enviar a Gerencia",
        type="primary",
    )

    if btn_firmar and id_seleccionado:
        firma_base64 = None
        if canvas_result.image_data is not None:
            firma_base64 = canvas_to_base64(canvas_result.image_data)

        if not firma_base64:
            st.error("❌ Debe dibujar su firma antes de resolver el expediente.")
        elif (
            denegar_permiso_banco(
                id_seleccionado, st.session_state["id_usuario"], motivo, firma_base64
            )
            if denegar
            else firmar_aprobacion_banco(
                id_seleccionado, st.session_state["id_usuario"], firma_base64
            )
        ):
            try:
                ruta = generar_pdf_solicitud(id_seleccionado)
                st.session_state["flash_coordinador"] = (
                    "success",
                    f"Expediente {id_seleccionado} "
                    f"{'denegado' if denegar else 'aprobado'} y firmado. "
                    f"PDF guardado en el repositorio ({ruta}).",
                )
            except Exception as e:
                st.session_state["flash_coordinador"] = (
                    "warning",
                    f"El expediente {id_seleccionado} fue "
                    f"{'denegado' if denegar else 'aprobado'}, pero no se "
                    f"pudo generar el PDF: {e}",
                )
            st.rerun()

    with st.expander(f"🕓 Historial de estados del expediente #{id_seleccionado}"):
        df_movimientos = obtener_historial(id_seleccionado)
        if df_movimientos.empty:
            st.info("Sin movimientos registrados.")
        else:
            st.dataframe(df_movimientos, hide_index=True, width="stretch")
