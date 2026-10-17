# Panel exclusivo donde el jefe inmediato GTC verá las solicitudes iongresadas del consultor.

import streamlit as st
import pandas as pd
from src.core.database import get_connection
from src.core.workflow import ESTADO_INGRESADA, ESTADO_PENDIENTE_APROBACION_GERENCIA
from src.core.security import rol_autorizado

def obtener_solicitudes_pendientes():
    """Recupera las solicitudes que acaban de ser ingresadas por el consultor."""
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
            df = pd.read_sql_query(query, conn, params=(ESTADO_INGRESADA,))
            conn.close()
            return df
        except Exception as e:
            st.error(f"Error al obtener datos: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def firmar_aprobacion_banco(id_solicitud):
    """Actualiza el estado simulando la firma digital del coordinador."""
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Mueve el documento a la bandeja de Gerencia SETESA
            cursor.execute("UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s", (ESTADO_PENDIENTE_APROBACION_GERENCIA, id_solicitud))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            st.error(f"Error al aplicar firma: {e}")
            return False

def mostrar_panel_coordinador():
    if not rol_autorizado(["Coordinador GTC"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Coordinador GTC.")
        return
    st.markdown("### 🏦 Portal de Aprobaciones - GTC")
    st.info("Módulo de revisión para Coordinadores. Las solicitudes aprobadas aquí serán enviadas a la Gerencia de SETESA para su validación final.")
    
    df_pendientes = obtener_solicitudes_pendientes()
    
    if df_pendientes.empty:
        st.success("Su bandeja está limpia. No hay solicitudes pendientes de revisión.")
        return
        
    st.write("**Bandeja de Entrada: Solicitudes de Consultores SETESA**")
    st.dataframe(df_pendientes, width="stretch", hide_index=True)
    
    st.write("---")
    st.markdown("#### 🖋️ Firma Digital de Aprobación")
    
    with st.form("form_firma_banco"):
        col1, col2 = st.columns([2, 1])
        with col1:
            id_seleccionado = st.selectbox("Seleccione el ID del expediente a aprobar:", df_pendientes['id_solicitud'].tolist())
        with col2:
            st.write("")
            st.write("")
            btn_firmar = st.form_submit_button("Otorgar Visto Bueno (Firmar)", type="primary", width="stretch")
            
        if btn_firmar and id_seleccionado:
            if firmar_aprobacion_banco(id_seleccionado):
                st.success(f"¡Expediente {id_seleccionado} firmado exitosamente! Se ha notificado a SETESA.")
                st.rerun()