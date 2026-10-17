#Ejecución del algoritmo de baja lógica semestral.

# Este script se conecta a PostgreSQL y ejecuta una actualización masiva (UPDATE) 
# sobre aquellos usuarios cuya ultima_actividad exceda los 6 meses (180 días)

import streamlit as st
import pandas as pd
from src.core.database import get_connection
from src.core.security import rol_autorizado

def ejecutar_depuracion_semestral():
    """Escanea la base de datos y aplica baja lógica a usuarios sin actividad en 6 meses."""
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # 1. Identificar a los usuarios que serán dados de baja (para mostrarlos en el reporte)
            query_select = """
                SELECT id_usuario, nombre_completo, correo_institucional, ultima_actividad
                FROM usuario
                WHERE estado_vigencia = TRUE 
                AND ultima_actividad < CURRENT_DATE - INTERVAL '6 months'
            """
            df_inactivos = pd.read_sql_query(query_select, conn)
            
            # 2. Ejecutar la actualización (Baja Lógica)
            query_update = """
                UPDATE usuario
                SET estado_vigencia = FALSE
                WHERE estado_vigencia = TRUE 
                AND ultima_actividad < CURRENT_DATE - INTERVAL '6 months'
            """
            cursor.execute(query_update)
            filas_afectadas = cursor.rowcount
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True, filas_afectadas, df_inactivos
        except Exception as e:
            st.error(f"Error al ejecutar el algoritmo de vigencia: {e}")
            return False, 0, pd.DataFrame()
    return False, 0, pd.DataFrame()

def mostrar_panel_vigencia():
    if not rol_autorizado(["Administrador"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Administrador.")
        return
    st.markdown("### 🛡️ Módulo de Auditoría y Vigencia de Usuarios")
    st.info("Este algoritmo identifica y desactiva automáticamente cuentas con más de 6 meses de inactividad, reemplazando la depuración manual.")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.write("Ejecutar el escaneo forzado de la base de datos:")
        btn_ejecutar = st.button("Ejecutar Algoritmo de Depuración", width="stretch", type="primary")
        
    if btn_ejecutar:
        exito, cantidad, df_afectados = ejecutar_depuracion_semestral()
        
        if exito:
            if cantidad > 0:
                st.success(f"¡Depuración exitosa! Se aplicó baja lógica a {cantidad} usuario(s).")
                st.write("**Usuarios desactivados en esta ejecución:**")
                st.dataframe(df_afectados, hide_index=True, width="stretch")
            else:
                st.info("Escaneo completado. No se encontraron usuarios con más de 6 meses de inactividad.")