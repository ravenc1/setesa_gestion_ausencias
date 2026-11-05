# Archivo principal d eintegración y navegación.

# Importación de módulos lógicos 
import streamlit as st
from src.core import auth
from src.core.logging_config import configurar_logging
from src.features import (
    registro,
    dashboard,
    vigencia,
    coordinador,
    feriados,
    gestion_usuarios,
    mis_datos,
    motivos,
    notificaciones,
    reasignacion,
)

configurar_logging()

st.set_page_config(page_title="SETESA Workflow", page_icon="🏢", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    auth.show_login()
else:
    # Fase 20: la sesión expira por inactividad o por duración máxima.
    from src.core import sesion

    motivo_expiracion = sesion.motivo_expiracion(st.session_state)
    if motivo_expiracion:
        st.session_state.clear()
        st.warning(sesion.mensaje_expiracion(motivo_expiracion))
        auth.show_login()
        st.stop()
    sesion.registrar_interaccion(st.session_state)

    # A-06: revalidar la vigencia en cada rerun para que una baja lógica
    # aplicada por Gerencia expulse también a las sesiones abiertas.
    from src.core.vigencia import usuario_activo

    if not usuario_activo(st.session_state.get('id_usuario')):
        st.session_state.clear()
        st.warning(
            "Su acceso fue desactivado (baja lógica), por no actualizar sus "
            "datos en el plazo de 6 meses o por decisión administrativa. "
            "Contacte a IT para solicitar la reactivación."
        )
        auth.show_login()
        st.stop()

    st.sidebar.title("Perfil de Usuario")
    st.sidebar.write(f"**Nombre:** {st.session_state['nombre']}")
    from src.core.security import nombre_rol_visible

    st.sidebar.write(f"**Rol:** {nombre_rol_visible(st.session_state['rol'])}")
    st.sidebar.write("---")

    # Fase 14: Consultor y Contabilidad tienen además "Mis datos"; Fase 18:
    # ambos reciben avisos al finalizar un expediente.
    seccion = None
    if st.session_state['rol'] in ('Consultor', 'Contabilidad'):
        etiqueta_avisos = notificaciones.etiqueta_menu(
            st.session_state.get('id_usuario')
        )
        seccion = st.sidebar.radio(
            "Sección",
            ["Principal", etiqueta_avisos, "🪪 Mis datos"],
            key="seccion_menu",
        )
        if seccion == etiqueta_avisos:
            seccion = "avisos"
        st.sidebar.write("---")

    if st.sidebar.button("Cerrar Sesión", width="stretch"):
        st.session_state.clear()
        st.rerun()
        
    mis_datos.mostrar_aviso_actualizacion()

    # ENRUTAMIENTO POR ROLES
    if seccion == "🪪 Mis datos":
        mis_datos.mostrar_mis_datos()

    elif seccion == "avisos":
        notificaciones.mostrar_notificaciones()

    elif st.session_state['rol'] == 'Consultor':
        st.title("Panel Operativo - Consultor Técnico")
        registro.mostrar_formulario()
        
    elif st.session_state['rol'] == 'Coordinador GTC':
        # NUEVA RUTA PARA EL CLIENTE
        coordinador.mostrar_panel_coordinador()
        
    elif st.session_state['rol'] == 'Contabilidad':
        # HU-03: repositorio de expedientes en modo consulta.
        st.title("Panel de Contabilidad y RR.HH. - SETESA")
        dashboard.mostrar_dashboard()

    elif st.session_state['rol'] == 'IT':
        # Fase 9: el rol IT solo administra cuentas.
        st.title("Panel de IT - Gestión de Usuarios")
        gestion_usuarios.mostrar_panel_usuarios()

    elif st.session_state['rol'] == 'Administrador':
        st.title("Panel Gerencial - SETESA")
        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            [
                "📊 Dashboard de Solicitudes",
                "🔁 Reasignar Coordinador",
                "🛡️ Control de Vigencia",
                "🗓️ Feriados",
                "🏷️ Motivos de ausencia",
            ]
        )
        with tab1:
            dashboard.mostrar_dashboard()
        with tab2:
            reasignacion.mostrar_panel_reasignacion()
        with tab3:
            vigencia.mostrar_panel_vigencia()
        with tab4:
            feriados.mostrar_panel_feriados()
        with tab5:
            motivos.mostrar_panel_motivos()
