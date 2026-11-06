# Archivo principal d eintegración y navegación.

# Importación de módulos lógicos 
import time

import streamlit as st
from src.core import auth
from src.core.logging_config import configurar_logging
from src.ui import estilos
from src.ui.pestanas import abierta, pestanas
from src.features import (
    registro,
    dashboard,
    vigencia,
    coordinador,
    feriados,
    gestion_usuarios,
    mi_cuenta,
    mis_datos,
    motivos,
    notificaciones,
    reasignacion,
)

configurar_logging()

st.set_page_config(
    page_title="SETESA Ausencias",
    page_icon=str(estilos.ICONO) if estilos.ICONO.exists() else "🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)
estilos.aplicar_estilos()

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

    # Fase 24: se consulta cada 30 s (no en cada clic) para no cargar la base.
    ahora = time.monotonic()
    if ahora - st.session_state.get('_vigencia_revisada', -999) > 30:
        st.session_state['_vigencia_revisada'] = ahora
        vigente = usuario_activo(st.session_state.get('id_usuario'))
    else:
        vigente = True
    if not vigente:
        st.session_state.clear()
        st.warning(
            "Su acceso fue desactivado (baja lógica), por no actualizar sus "
            "datos en el plazo de 6 meses o por decisión administrativa. "
            "Contacte a IT para solicitar la reactivación."
        )
        auth.show_login()
        st.stop()

    from src.core.security import nombre_rol_visible
    estilos.perfil_lateral(
        st.session_state['nombre'], nombre_rol_visible(st.session_state['rol'])
    )

    # Fase 14: Consultor y Contabilidad tienen además "Mis datos"; Fase 18:
    # ambos reciben avisos; Fase 24: todos pueden cambiar su contraseña.
    seccion = None
    if st.session_state.get('debe_cambiar_password'):
        pass  # solo se muestra el cambio obligatorio (más abajo)
    elif st.session_state['rol'] in ('Consultor', 'Contabilidad'):
        etiqueta_avisos = notificaciones.etiqueta_menu(
            st.session_state.get('id_usuario')
        )
        seccion = st.sidebar.radio(
            "Sección",
            ["Principal", etiqueta_avisos, "👤 Mis datos", "🔑 Mi contraseña"],
            key="seccion_menu",
        )
        if seccion == etiqueta_avisos:
            seccion = "avisos"
        st.sidebar.write("---")
    else:
        seccion = st.sidebar.radio(
            "Sección", ["Principal", "🔑 Mi contraseña"], key="seccion_menu"
        )
        st.sidebar.write("---")

    if st.sidebar.button("Cerrar Sesión", width="stretch"):
        st.session_state.clear()
        st.rerun()
        
    # Fase 24: tras un restablecimiento de IT, la contraseña temporal debe cambiarse.
    if st.session_state.get('debe_cambiar_password'):
        estilos.encabezado(
            "Cambio de contraseña obligatorio",
            "Elija una contraseña propia para empezar a usar la plataforma.",
        )
        mi_cuenta.mostrar_cambio_password(obligatorio=True)
        estilos.pie_de_pagina()
        st.stop()

    mis_datos.mostrar_aviso_actualizacion()

    # ENRUTAMIENTO POR ROLES
    if seccion == "🔑 Mi contraseña":
        mi_cuenta.mostrar_cambio_password()

    elif seccion == "👤 Mis datos":
        mis_datos.mostrar_mis_datos()

    elif seccion == "avisos":
        notificaciones.mostrar_notificaciones()

    elif st.session_state['rol'] == 'Consultor':
        estilos.encabezado(
            "Panel Operativo - Consultor Técnico",
            "Registre y dé seguimiento a sus solicitudes de ausencia.",
        )
        registro.mostrar_formulario()
        
    elif st.session_state['rol'] == 'Coordinador GTC':
        # NUEVA RUTA PARA EL CLIENTE
        estilos.encabezado(
            "Portal del Coordinador GTC",
            "Revise y resuelva las solicitudes de los consultores de su equipo.",
        )
        coordinador.mostrar_panel_coordinador()
        
    elif st.session_state['rol'] == 'Contabilidad':
        # HU-03: repositorio de expedientes en modo consulta.
        estilos.encabezado(
            "Panel de Contabilidad y RR.HH. - SETESA",
            "Consulta y control de expedientes de ausencia.",
        )
        dashboard.mostrar_dashboard()

    elif st.session_state['rol'] == 'IT':
        # Fase 9: el rol IT solo administra cuentas.
        estilos.encabezado(
            "Panel de IT - Gestión de Usuarios",
            "Altas, bajas y accesos de las cuentas del sistema.",
        )
        gestion_usuarios.mostrar_panel_usuarios()

    elif st.session_state['rol'] == 'Administrador':
        estilos.encabezado(
            "Panel Gerencial - SETESA",
            "Autorizaciones, indicadores y catálogos de la organización.",
        )
        tab1, tab2, tab3, tab4, tab5 = pestanas(
            [
                "📊 Dashboard de Solicitudes",
                "🔁 Reasignar Coordinador",
                "🛡️ Control de Vigencia",
                "🗓️ Feriados",
                "🏷️ Motivos de ausencia",
            ],
            "tabs_gerencia",
        )
        with tab1:
            if abierta(tab1):
                dashboard.mostrar_dashboard()
        with tab2:
            if abierta(tab2):
                reasignacion.mostrar_panel_reasignacion()
        with tab3:
            if abierta(tab3):
                vigencia.mostrar_panel_vigencia()
        with tab4:
            if abierta(tab4):
                feriados.mostrar_panel_feriados()
        with tab5:
            if abierta(tab5):
                motivos.mostrar_panel_motivos()

    estilos.pie_de_pagina()
