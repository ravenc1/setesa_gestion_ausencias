# Componente para ver y adjuntar evidencias de un expediente (Fase 18).

import streamlit as st

from src.core.evidencias import (
    EvidenciaError,
    agregar_evidencias,
    descargar_evidencia,
    listar_evidencias,
)


def mostrar_evidencias(id_solicitud, id_usuario, contexto, permitir_agregar=False):
    """Lista las evidencias con su descarga; el consultor puede agregar más."""
    try:
        df = listar_evidencias(id_solicitud, id_usuario)
    except EvidenciaError as e:
        st.info(str(e))
        return
    except Exception as e:
        st.warning(f"No se pudieron cargar las evidencias: {e}")
        return

    if df.empty:
        st.caption("Este expediente no tiene evidencias adjuntas.")
    for fila in df.itertuples():
        col_nombre, col_boton = st.columns([3, 1])
        col_nombre.write(
            f"📄 {fila.nombre_original} · {fila.tamano / 1024:.0f} KB · "
            f"{fila.fecha:%d/%m/%Y %H:%M}"
        )
        clave_estado = f"ev_{contexto}_{fila.id_evidencia}"
        if col_boton.button("Preparar descarga", key=f"btn_{clave_estado}"):
            try:
                st.session_state[clave_estado] = descargar_evidencia(
                    int(fila.id_evidencia), id_usuario
                )
            except Exception as e:
                st.error(f"No se pudo descargar: {e}")
        if clave_estado in st.session_state:
            nombre, tipo, contenido = st.session_state[clave_estado]
            col_boton.download_button(
                "📥 Descargar", data=contenido, file_name=nombre, mime=tipo,
                key=f"dl_{clave_estado}",
            )

    if not permitir_agregar:
        return
    with st.form(f"form_evidencias_{contexto}_{id_solicitud}", clear_on_submit=True):
        nuevos = st.file_uploader(
            "Agregar evidencias (PDF, JPG o PNG; máximo 5 MB cada una)",
            type=["pdf", "jpg", "jpeg", "png"],
            accept_multiple_files=True,
        )
        enviar = st.form_submit_button("📎 Adjuntar")
    if enviar and nuevos:
        try:
            cantidad = agregar_evidencias(
                id_solicitud, id_usuario, [(a.name, a.getvalue()) for a in nuevos]
            )
        except EvidenciaError as e:
            st.error(f"❌ {e}")
        except Exception as e:
            st.error(f"No se pudieron adjuntar las evidencias: {e}")
        else:
            st.success(f"{cantidad} evidencia(s) adjuntadas.")
            st.rerun()
