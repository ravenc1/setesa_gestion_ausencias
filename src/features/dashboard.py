# Trazabilidad de solicitudes y filtrado.

import streamlit as st
import pandas as pd
from src.core.database import get_connection
from src.core.workflow import (
    ESTADO_INGRESADA,
    ESTADO_FINALIZADA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
)
from src.core.security import rol_autorizado

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

def actualizar_estado(id_solicitud, nuevo_estado):
    """Ejecuta un UPDATE en PostgreSQL para avanzar la solicitud en el workflow."""
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s", (nuevo_estado, id_solicitud))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            st.error(f"Error al actualizar estado: {e}")
            return False

def mostrar_dashboard():
    if not rol_autorizado(["Administrador"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Administrador.")
        return
    st.markdown("### Panel de Control Gerencial y Aprobaciones")
    st.info("Módulo de trazabilidad y gobernanza sobre las incidencias del personal externo.")

    df_solicitudes = obtener_solicitudes()

    if df_solicitudes.empty:
        st.warning("Aún no hay solicitudes de ausencia registradas en la base de datos.")
        return

    # 1. Indicadores Clave (KPIs)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Expedientes", len(df_solicitudes))
    col2.metric("Nuevas (Ingresadas)", len(df_solicitudes[df_solicitudes['estado_workflow'] == ESTADO_INGRESADA]))
    col3.metric("Finalizadas / Aprobadas", len(df_solicitudes[df_solicitudes['estado_workflow'] == ESTADO_FINALIZADA]))

    st.write("---")
    st.markdown("#### Repositorio Histórico y Filtros")
    
    # 2. Filtros de Búsqueda
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        filtro_nombre = st.text_input("🔍 Buscar por nombre de colaborador")
    with f_col2:
        estados_disponibles = ["Todos"] + list(df_solicitudes['estado_workflow'].unique())
        filtro_estado = st.selectbox("📌 Filtrar por Estado del Workflow", estados_disponibles)

    # Aplicar filtros al dataframe
    df_filtrado = df_solicitudes.copy()
    if filtro_nombre:
        df_filtrado = df_filtrado[df_filtrado['nombre_completo'].str.contains(filtro_nombre, case=False, na=False)]
    if filtro_estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['estado_workflow'] == filtro_estado]

    # Mostrar la tabla de datos
    st.dataframe(df_filtrado, width="stretch", hide_index=True)

    st.write("---")
    st.markdown("#### Gestión de Workflow (Autorizaciones)")
    
    # 3. Formulario para aprobar o cambiar el estado de una solicitud
    with st.form("form_workflow"):
        w_col1, w_col2 = st.columns(2)
        with w_col1:
            id_seleccionado = st.selectbox("ID de la Solicitud a Actualizar", df_filtrado['id_solicitud'].tolist())
        with w_col2:
            nuevo_estado = st.selectbox(
                "Mover al Nuevo Estado", 
                [ESTADO_PENDIENTE_FIRMA_COORDINADOR, ESTADO_PENDIENTE_APROBACION_GERENCIA, ESTADO_FINALIZADA]
            )
        
        btn_actualizar = st.form_submit_button("Actualizar Estado en Base de Datos")
        
        if btn_actualizar and id_seleccionado:
            exito = actualizar_estado(id_seleccionado, nuevo_estado)
            if exito:
                st.success(f"El expediente ID: {id_seleccionado} fue actualizado a '{nuevo_estado}' exitosamente.")
                st.rerun()