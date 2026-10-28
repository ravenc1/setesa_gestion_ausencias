# Formulario interactivo de captura de datos de ausencia.

import streamlit as st
import datetime
import pandas as pd
from src.services.utils_firma import canvas_to_base64
from src.core.crypto import descifrar_dataframe
from src.core.database import get_engine
from src.core.logging_config import obtener_logger
from src.services.documentos import generar_pdf_solicitud
from src.core.security import rol_autorizado
from src.core.catalogos import OPCIONES_AUSENCIA
from src.core.feriados import fechas_feriados
from src.core.usuarios import listar_coordinadores
from src.core.utils import calcular_dias_habiles
from src.core.vacaciones import TIPO_VACACION, obtener_saldo_vacaciones
from src.core.validaciones import ValidacionError
from src.core.solicitudes import registrar_solicitud, obtener_historial

logger = obtener_logger("setesa.registro")

def registrar_solicitud_firmada(id_us, tipo, f_ini, f_fin, jefe, puesto, codigo, dias, exp, firma_b64):
    """Inserta la solicitud y su historial en una sola transacción.

    Devuelve el id_solicitud generado o None si falla. El servicio deja la
    solicitud en 'Pendiente de Firma Coordinador' (decisión D-01, opción C).
    """
    try:
        return registrar_solicitud(
            id_us, tipo, f_ini, f_fin, jefe, puesto, codigo, dias, exp, firma_b64
        )
    except ValidacionError as e:
        st.error(f"❌ {e}")
        return None
    except Exception as e:
        logger.exception("Error al registrar la solicitud")
        st.error(f"Error BD: {e}")
        return None

def obtener_mis_solicitudes(id_usuario):
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    # Se agregaron las columnas de firma al SELECT para poder inyectarlas en el PDF histórico.
    query = """
        SELECT id_solicitud, fecha_creacion, tipo_ausencia, fecha_inicio, fecha_fin,
               dias_solicitados, estado_workflow, jefe_gtc, puesto, codigo_empleado,
               explicacion, firma_empleado, firma_jefe_gtc, firma_gerencia
        FROM solicitud
        WHERE id_usuario = %s ORDER BY fecha_creacion DESC
    """
    df = pd.read_sql_query(query, engine, params=(id_usuario,))
    # H-11: los campos sensibles se descifran solo al mostrarlos o generar el PDF.
    return descifrar_dataframe(df)

def mostrar_formulario():
    if not rol_autorizado(["Consultor"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Consultor.")
        return
    from streamlit_drawable_canvas import st_canvas  # import perezoso: requiere el runtime
    st.markdown("### Panel Operativo - Acción de Personal")

    # RF-01: saldo de vacaciones del consultor (D-03: asignado - usado).
    saldo_vacaciones = None
    try:
        saldo_vacaciones = obtener_saldo_vacaciones(st.session_state["id_usuario"])
    except Exception as e:
        st.warning(f"No se pudo calcular el saldo de vacaciones: {e}")
    else:
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Vacaciones disponibles", saldo_vacaciones["disponibles"])
        col_b.metric("Días asignados", saldo_vacaciones["asignados"])
        col_c.metric("Días usados", saldo_vacaciones["usados"])
        st.caption(
            f"Saldo del año {saldo_vacaciones['anio']} "
            "(días asignados menos días solicitados como VACACION)."
        )
        if saldo_vacaciones["disponibles"] < 0:
            st.error(
                "Su saldo de vacaciones está excedido; contacte a Gerencia "
                "antes de registrar otra solicitud."
            )
    
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
            st.success("✅ ¡Su solicitud fue firmada electrónicamente y enviada al Coordinador GTC para su visto bueno!")
            if st.session_state.pdf_generado:
                with open(st.session_state.pdf_generado, "rb") as f:
                    st.download_button("📥 Descargar Comprobante (PDF)", data=f, file_name="Accion_Personal_SETESA.pdf", mime="application/pdf", type="primary")
            else:
                st.warning("La solicitud quedó registrada, pero el PDF no está disponible. Consulte la pestaña de historial.")
            st.write("---")
            if st.button("⬅️ Regresar y redactar una nueva solicitud"):
                st.session_state.solicitud_enviada = False
                st.session_state.mostrar_canvas_firma = False
                st.rerun()
        else:
            st.info("Complete el formulario. Al firmar electrónicamente, la solicitud se enviará al Coordinador GTC para su visto bueno.")
            col1, col2 = st.columns(2)
            with col1:
                coordinadores = listar_coordinadores()
                opciones_jefe = coordinadores["nombre_completo"].tolist()
                if opciones_jefe:
                    jefe_gtc = st.selectbox(
                        "PARA: (Jefe Inmediato GTC)", opciones_jefe
                    )
                else:
                    st.warning(
                        "No hay usuarios vigentes con rol Coordinador GTC. "
                        "Escriba el nombre manualmente."
                    )
                    jefe_gtc = st.text_input(
                        "PARA: (Nombre del Jefe Inmediato GTC)"
                    )
                puesto = st.text_input("PUESTO:")
                fecha_inicio = st.date_input("Fecha de Inicio (Del:)", min_value=datetime.date.today())
            with col2:
                codigo = st.text_input("CÓDIGO:")
                tipo_ausencia = st.selectbox("NATURALEZA DE LA ACCIÓN:", OPCIONES_AUSENCIA)
                fecha_fin = st.date_input(
                    "Fecha de Fin (Al:)",
                    value=fecha_inicio,
                    min_value=fecha_inicio,
                )

            feriados_rango = set()
            if fecha_fin < fecha_inicio:
                st.error(
                    "❌ La fecha de fin no puede ser anterior a la fecha de inicio."
                )
                dias_solicitados = 0
            else:
                feriados_rango = fechas_feriados(fecha_inicio, fecha_fin)
                dias_solicitados = calcular_dias_habiles(
                    fecha_inicio, fecha_fin, feriados_rango
                )
            st.metric(label="Cantidad de Días Hábiles a Solicitar", value=dias_solicitados)
            if feriados_rango:
                st.caption(
                    "Se excluyen "
                    f"{len(feriados_rango)} feriado(s): "
                    + ", ".join(sorted(f.isoformat() for f in feriados_rango))
                    + "."
                )
            
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
                            st.error("❌ El rango seleccionado no contiene días hábiles (solo fines de semana o feriados).")
                        elif (
                            tipo_ausencia == TIPO_VACACION
                            and saldo_vacaciones is not None
                            and dias_solicitados > saldo_vacaciones["disponibles"]
                        ):
                            st.error(
                                "❌ Saldo de vacaciones insuficiente: solicita "
                                f"{dias_solicitados} día(s) y solo tiene "
                                f"{saldo_vacaciones['disponibles']} disponible(s)."
                            )
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
                            id_us = st.session_state['id_usuario']
                            
                            id_solicitud = registrar_solicitud_firmada(
                                id_us, tipo_ausencia, fecha_inicio, fecha_fin,
                                jefe_gtc, puesto, codigo, dias_solicitados,
                                explicacion, firma_base64,
                            )
                            if id_solicitud:
                                # El servicio toma los datos ya persistidos y
                                # guarda la ruta en solicitud.ruta_pdf.
                                ruta = None
                                try:
                                    ruta = generar_pdf_solicitud(id_solicitud)
                                except Exception as e:
                                    st.warning(
                                        "La solicitud se guardó, pero no se pudo "
                                        f"generar el PDF: {e}"
                                    )
                                st.session_state.pdf_generado = ruta or ""
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
                # Regeneración desde la BD: incluye las firmas ya capturadas y
                # actualiza solicitud.ruta_pdf.
                try:
                    pdf_historial = generar_pdf_solicitud(id_descarga)
                except Exception as e:
                    st.error(f"No se pudo generar el PDF: {e}")
                else:
                    with open(pdf_historial, "rb") as f:
                        st.download_button(f"📥 Descargar Expediente #{id_descarga} ({fila['estado_workflow']})", data=f, file_name=f"Expediente_{id_descarga}.pdf", mime="application/pdf", type="primary")

            with st.expander(f"🕓 Historial de estados del expediente #{id_descarga}"):
                df_movimientos = obtener_historial(id_descarga)
                if df_movimientos.empty:
                    st.info("Sin movimientos registrados.")
                else:
                    st.dataframe(df_movimientos, hide_index=True, width="stretch")
        else:
            st.info("Aún no tienes solicitudes registradas.")