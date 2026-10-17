# Formulario interactivo de captura de datos de ausencia.

import streamlit as st
import datetime
import pandas as pd
from src.services.utils_firma import canvas_to_base64
from src.core.database import get_connection
from src.services.motor_pdf import generar_pdf_accion_personal
from src.core.workflow import ESTADO_INGRESADA
from src.core.security import rol_autorizado
from src.core.catalogos import OPCIONES_AUSENCIA
from src.core.utils import calcular_dias_habiles

def registrar_solicitud_firmada(id_us, tipo, f_ini, f_fin, jefe, puesto, codigo, dias, exp, firma_b64):
    """Inserta la solicitud en PostgreSQL incluyendo la firma manuscrita digitalizada."""
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO solicitud 
                (id_usuario, tipo_ausencia, fecha_inicio, fecha_fin, estado_workflow, jefe_gtc, puesto, codigo_empleado, dias_solicitados, explicacion, firma_empleado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (id_us, tipo, f_ini, f_fin, ESTADO_INGRESADA, jefe, puesto, codigo, dias, exp, firma_b64))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            st.error(f"Error BD: {e}")
            return False

def obtener_mis_solicitudes(id_usuario):
    conn = get_connection()
    if conn:
        # Se agregaron las columnas de firma al SELECT para poder inyectarlas en el PDF histórico
        query = """
            SELECT id_solicitud, fecha_creacion, tipo_ausencia, fecha_inicio, fecha_fin, 
                   dias_solicitados, estado_workflow, jefe_gtc, puesto, codigo_empleado, 
                   explicacion, firma_empleado, firma_jefe_gtc, firma_gerencia 
            FROM solicitud 
            WHERE id_usuario = %s ORDER BY fecha_creacion DESC
        """
        df = pd.read_sql_query(query, conn, params=(id_usuario,))
        conn.close()
        return df
    return pd.DataFrame()

def mostrar_formulario():
    if not rol_autorizado(["Consultor"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Consultor.")
        return
    from streamlit_drawable_canvas import st_canvas  # import perezoso: requiere el runtime
    st.markdown("### Panel Operativo - Acción de Personal")
    
    # Manejo de estados para la navegación
    if 'solicitud_enviada' not in st.session_state:
        st.session_state.solicitud_enviada = False
        st.session_state.pdf_generado = ""
    if 'mostrar_canvas_firma' not in st.session_state:
        st.session_state.mostrar_canvas_firma = False

    tab1, tab2 = st.tabs(["📝 Generar y Firmar Solicitud", "🗂 Mis Solicitudes (Historial)"])
    
    with tab1:
        if st.session_state.solicitud_enviada:
            # Mensaje de éxito actualizado
            st.success("✅ ¡Su solicitud fue firmada electrónicamente y enviada a su Jefe Inmediato GTC y a Gerencia SETESA para su revisión!")
            with open(st.session_state.pdf_generado, "rb") as f:
                st.download_button("📥 Descargar Comprobante (PDF)", data=f, file_name="Accion_Personal_SETESA.pdf", mime="application/pdf", type="primary")
            st.write("---")
            if st.button("⬅️ Regresar y redactar una nueva solicitud"):
                st.session_state.solicitud_enviada = False
                st.session_state.mostrar_canvas_firma = False
                st.rerun()
        else:
            st.info("Complete el formulario. Al firmar electrónicamente, el documento oficial se remitirá al banco.")
            col1, col2 = st.columns(2)
            with col1:
                jefe_gtc = st.text_input("PARA: (Nombre del Jefe Inmediato GTC)")
                puesto = st.text_input("PUESTO:")
                fecha_inicio = st.date_input("Fecha de Inicio (Del:)", min_value=datetime.date.today())
            with col2:
                codigo = st.text_input("CÓDIGO:")
                tipo_ausencia = st.selectbox("NATURALEZA DE LA ACCIÓN:", OPCIONES_AUSENCIA)
                fecha_fin = st.date_input("Fecha de Fin (Al:)", min_value=fecha_inicio)
            
            dias_solicitados = calcular_dias_habiles(fecha_inicio, fecha_fin)
            st.metric(label="Cantidad de Días Hábiles a Solicitar", value=dias_solicitados)
            
            explicacion = st.text_area("EXPLICACIÓN DE LA ACCIÓN:", height=100)
            st.write("---")
            
            # --- FLUJO DE DOS PASOS ESTRICTO ---
            if not st.session_state.mostrar_canvas_firma:
                col_btn, _ = st.columns([1, 3]) 
                with col_btn:
                    if st.button("✍️ Firmar Electrónicamente", type="primary"):
                        if not jefe_gtc or not explicacion:
                            st.error("❌ Llene todos los campos para proceder.")
                        elif dias_solicitados == 0:
                            st.error("❌ El rango corresponde solo a fines de semana.")
                        else:
                            st.session_state.mostrar_canvas_firma = True
                            st.rerun()
            else:
                st.markdown("#### 🖋️ Firma del Consultor Técnico")
                st.info("💡 Sugerencia: Dibuje su firma en el centro del recuadro sin tocar los bordes.")
                
                # Integración del Canvas configurado como transparente
                canvas_result = st_canvas(
                    fill_color="rgba(255, 165, 0, 0.3)",  
                    stroke_width=3,  # Se subió el grosor a 3 para que se vea más nítido en el PDF
                    stroke_color="#000000",
                    background_color="rgba(0, 0, 0, 0)",  # <-- VITAL: Fondo transparente
                    height=100,  # <-- Se redujo la altura para que no quede estirado
                    width=300,   # <-- Se redujo el ancho para evitar salirse del margen
                    drawing_mode="freedraw",
                    key="canvas_firma_consultor",
                    return_image_data=True
                )
                
                st.markdown("⚠️ *Su sesión autenticada y su trazo actuarán como su Firma Electrónica válida.*")
                
                col_enviar, col_cancelar, _ = st.columns([1.5, 1, 1.5])
                
                with col_enviar:
                    # Texto del botón actualizado
                    if st.button("Enviar", type="primary"):
                        firma_base64 = None
                        if canvas_result.image_data is not None:
                            firma_base64 = canvas_to_base64(canvas_result.image_data)
                        
                        if not firma_base64:
                            st.error("❌ Debe dibujar su firma en el recuadro antes de enviar.")
                        else:
                            nom = st.session_state['nombre']
                            id_us = st.session_state['id_usuario']
                            
                            if registrar_solicitud_firmada(id_us, tipo_ausencia, fecha_inicio, fecha_fin, jefe_gtc, puesto, codigo, dias_solicitados, explicacion, firma_base64):
                                # Pasamos explícitamente la fecha de hoy y la firma base64 al PDF
                                fecha_actual = datetime.date.today().strftime("%Y-%m-%d")
                                ruta = generar_pdf_accion_personal(
                                    nom, jefe_gtc, puesto, codigo, tipo_ausencia, 
                                    str(fecha_inicio), str(fecha_fin), dias_solicitados, explicacion, 
                                    ESTADO_INGRESADA,
                                    fecha_creacion=fecha_actual,
                                    firma_empleado_b64=firma_base64
                                )
                                st.session_state.pdf_generado = ruta
                                st.session_state.solicitud_enviada = True
                                st.session_state.mostrar_canvas_firma = False
                                st.rerun()
                
                with col_cancelar:
                    if st.button("Cancelar"):
                        st.session_state.mostrar_canvas_firma = False
                        st.rerun()

    with tab2:
        st.markdown("#### Historial de Mis Solicitudes (Detalle Completo)")
        df_historial = obtener_mis_solicitudes(st.session_state['id_usuario'])
        
        if not df_historial.empty:
            st.dataframe(df_historial, hide_index=True, width="stretch")
            st.write("---")
            st.markdown("#### 📥 Recuperar Documento (Firmas Dinámicas)")
            st.info("Descargue el PDF actualizado con las firmas correspondientes al estado actual del flujo.")
            
            id_descarga = st.selectbox("Seleccione el ID de la solicitud a descargar:", df_historial['id_solicitud'])
            fila = df_historial[df_historial['id_solicitud'] == id_descarga].iloc[0]
            
            if st.button("Generar y Descargar PDF Actualizado"):
                # Regeneración del PDF extrayendo las fechas y firmas directamente del Dataframe (BD)
                pdf_historial = generar_pdf_accion_personal(
                    st.session_state['nombre'], fila['jefe_gtc'], fila['puesto'], fila['codigo_empleado'], 
                    fila['tipo_ausencia'], fila['fecha_inicio'], fila['fecha_fin'], fila['dias_solicitados'], 
                    fila['explicacion'], fila['estado_workflow'],
                    fecha_creacion=str(fila['fecha_creacion']),
                    firma_empleado_b64=fila.get('firma_empleado'),
                    firma_jefe_b64=fila.get('firma_jefe_gtc'),
                    firma_gerencia_b64=fila.get('firma_gerencia')
                )
                with open(pdf_historial, "rb") as f:
                    st.download_button(f"📥 Descargar Expediente #{id_descarga} ({fila['estado_workflow']})", data=f, file_name=f"Expediente_{id_descarga}.pdf", mime="application/pdf", type="primary")
        else:
            st.info("Aún no tienes solicitudes registradas.")