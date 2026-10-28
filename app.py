# Archivo principal d eintegración y navegación.

# Importación de módulos lógicos 
import streamlit as st
from src.core import auth
from src.features import registro, dashboard, vigencia, coordinador, feriados

st.set_page_config(page_title="SETESA Workflow", page_icon="🏢", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    auth.show_login()
else:
    # A-06: revalidar la vigencia en cada rerun para que una baja lógica
    # aplicada por Gerencia expulse también a las sesiones abiertas.
    from src.core.vigencia import usuario_activo

    if not usuario_activo(st.session_state.get('id_usuario')):
        st.session_state.clear()
        st.warning(
            "Su acceso fue desactivado por inactividad (baja lógica). "
            "Contacte a Gerencia para solicitar la reactivación."
        )
        auth.show_login()
        st.stop()

    st.sidebar.title("Perfil de Usuario")
    st.sidebar.write(f"**Nombre:** {st.session_state['nombre']}")
    st.sidebar.write(f"**Rol RBAC:** {st.session_state['rol']}")
    st.sidebar.write("---")
    
    if st.sidebar.button("Cerrar Sesión", width="stretch"):
        st.session_state.clear()
        st.rerun()
        
    # ENRUTAMIENTO POR ROLES
    if st.session_state['rol'] == 'Consultor':
        st.title("Panel Operativo - Consultor Técnico")
        registro.mostrar_formulario()
        
    elif st.session_state['rol'] == 'Coordinador GTC':
        # NUEVA RUTA PARA EL CLIENTE
        coordinador.mostrar_panel_coordinador()
        
    elif st.session_state['rol'] == 'Administrador':
        st.title("Panel Gerencial - SETESA")
        tab1, tab2, tab3 = st.tabs(
            [
                "📊 Dashboard de Solicitudes",
                "🛡️ Control de Vigencia",
                "🗓️ Feriados",
            ]
        )
        with tab1:
            dashboard.mostrar_dashboard()
        with tab2:
            vigencia.mostrar_panel_vigencia()
        with tab3:
            feriados.mostrar_panel_feriados()
