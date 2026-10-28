# Trazabilidad de solicitudes y filtrado.

import streamlit as st
import pandas as pd

from src.core.database import get_connection
from src.core.workflow import (
    ESTADOS_WORKFLOW,
    ESTADO_FINALIZADA,
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


def obtener_solicitudes():
    """Recupera todas las solicitudes con un JOIN a la tabla de usuarios."""
    conn = get_connection()
    if conn:
        try:
            query = """
                SELECT s.id_solicitud, u.nombre_completo, s.tipo_ausencia,
                       s.fecha_inicio, s.fecha_fin, s.estado_workflow, s.fecha_creacion
                FROM solicitud s
                JOIN usuario u ON s.id_usuario = u.id_usuario
                ORDER BY s.fecha_creacion DESC
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            st.error(f"Error al obtener solicitudes: {e}")
            return pd.DataFrame()
    return pd.DataFrame()


def mostrar_dashboard():
    if not rol_autorizado(["Administrador"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Administrador.")
        return

    st.markdown("### Panel de Control Gerencial y Aprobaciones")
    flash = st.session_state.pop("flash_gerencia", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.info("Módulo de trazabilidad y gobernanza sobre las incidencias del personal externo.")

    df_solicitudes = obtener_solicitudes()

    if df_solicitudes.empty:
        st.warning("Aún no hay solicitudes de ausencia registradas en la base de datos.")
        return

    invalidos = df_solicitudes[
        ~df_solicitudes["estado_workflow"].isin(ESTADOS_WORKFLOW)
    ]
    if not invalidos.empty:
        st.warning(
            "Hay solicitudes con estados fuera del catálogo. "
            "Ejecute la migración de datos antes de continuar."
        )
        st.dataframe(invalidos, hide_index=True, width="stretch")

    # 1. Indicadores Clave (KPIs)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Expedientes", len(df_solicitudes))
    col2.metric(
        "Pendientes Coordinador",
        len(
            df_solicitudes[
                df_solicitudes["estado_workflow"]
                == ESTADO_PENDIENTE_FIRMA_COORDINADOR
            ]
        ),
    )
    col3.metric(
        "Pendientes Gerencia",
        len(
            df_solicitudes[
                df_solicitudes["estado_workflow"]
                == ESTADO_PENDIENTE_APROBACION_GERENCIA
            ]
        ),
    )
    col4.metric(
        "Finalizadas",
        len(df_solicitudes[df_solicitudes["estado_workflow"] == ESTADO_FINALIZADA]),
    )

    st.write("---")
    st.markdown("#### Repositorio Histórico y Filtros")

    # 2. Filtros de Búsqueda
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        filtro_nombre = st.text_input("🔍 Buscar por nombre de colaborador")
    with f_col2:
        estados_disponibles = ["Todos"] + ESTADOS_WORKFLOW
        filtro_estado = st.selectbox("📌 Filtrar por Estado del Workflow", estados_disponibles)

    # Aplicar filtros al dataframe
    df_filtrado = df_solicitudes.copy()
    if filtro_nombre:
        df_filtrado = df_filtrado[
            df_filtrado["nombre_completo"].str.contains(
                filtro_nombre, case=False, na=False
            )
        ]
    if filtro_estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["estado_workflow"] == filtro_estado]

    # Mostrar la tabla de datos
    st.dataframe(df_filtrado, width="stretch", hide_index=True)

    if df_filtrado.empty:
        st.info("No hay expedientes que coincidan con los filtros seleccionados.")
        return

    st.write("---")
    st.markdown("#### Gestión de Workflow (Autorización de Gerencia)")

    # 3. Solo se permite la transición que corresponde a Gerencia.
    id_seleccionado = st.selectbox(
        "ID de la Solicitud", df_filtrado["id_solicitud"].tolist()
    )
    fila = df_filtrado[df_filtrado["id_solicitud"] == id_seleccionado].iloc[0]
    estado_actual = fila["estado_workflow"]

    st.write(f"**Estado actual:** {estado_actual}")

    if estado_actual == ESTADO_PENDIENTE_APROBACION_GERENCIA:
        from streamlit_drawable_canvas import st_canvas  # import perezoso

        st.info(
            "💡 Dibuje su firma en el recuadro; quedará estampada en el PDF "
            "oficial al finalizar el expediente."
        )
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=3,
            stroke_color="#000000",
            background_color="rgba(0, 0, 0, 0)",
            height=100,
            width=300,
            drawing_mode="freedraw",
            key=f"canvas_gerencia_{id_seleccionado}",
            return_image_data=True,
        )
        observacion = st.text_input("Observación de Gerencia (opcional)")
        btn_actualizar = st.button(
            "✅ Aprobar, Firmar y Finalizar Expediente", type="primary"
        )

        if btn_actualizar and id_seleccionado:
            firma_base64 = None
            if canvas_result.image_data is not None:
                firma_base64 = canvas_to_base64(canvas_result.image_data)

            if not firma_base64:
                st.error("❌ Debe dibujar su firma antes de finalizar el expediente.")
            else:
                try:
                    cambiar_estado(
                        id_seleccionado,
                        ESTADO_FINALIZADA,
                        st.session_state["id_usuario"],
                        observacion or "Aprobación final de Gerencia.",
                        firma_b64=firma_base64,
                    )
                except FirmaRequerida as e:
                    st.error(f"Debe firmar el expediente: {e}")
                except TransicionInvalida as e:
                    st.error(f"No se puede finalizar: {e}")
                except Exception as e:
                    st.error(f"Error al actualizar el estado: {e}")
                else:
                    try:
                        ruta = generar_pdf_solicitud(id_seleccionado)
                        st.session_state["flash_gerencia"] = (
                            "success",
                            f"El expediente #{id_seleccionado} fue finalizado y "
                            f"firmado. PDF actualizado en {ruta}.",
                        )
                    except Exception as e:
                        st.session_state["flash_gerencia"] = (
                            "warning",
                            f"El expediente #{id_seleccionado} fue finalizado, "
                            f"pero no se pudo generar el PDF: {e}",
                        )
                    st.rerun()
    elif estado_actual == ESTADO_FINALIZADA:
        st.info("La solicitud está finalizada; no admite más cambios.")
    else:
        st.info(
            "Esta solicitud aún debe ser firmada por el Coordinador GTC. "
            "Gerencia solo puede autorizar expedientes que lleguen a "
            "'Pendiente de Aprobación Gerencia'."
        )

    with st.expander(f"🕓 Historial de estados del expediente #{id_seleccionado}"):
        df_movimientos = obtener_historial(id_seleccionado)
        if df_movimientos.empty:
            st.info("Sin movimientos registrados.")
        else:
            st.dataframe(df_movimientos, hide_index=True, width="stretch")
