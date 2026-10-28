# Validación de sesión y Control de Acceso Basado en Roles.

import streamlit as st
from src.core.database import get_connection
from src.core.logging_config import obtener_logger
from src.core.security import verify_or_upgrade
from src.core.vigencia import ejecutar_si_corresponde, marcar_actividad

logger = obtener_logger("setesa.auth")

def login_user(email, password):
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        # A-05: el correo se normaliza para evitar fallos por mayúsculas/espacios.
        correo = (email or "").strip().lower()
        query = """
            SELECT u.id_usuario, u.nombre_completo, u.estado_vigencia, r.nombre_rol, u.password_hash
            FROM usuario u
            JOIN rol r ON u.id_rol = r.id_rol
            WHERE LOWER(u.correo_institucional) = %s
        """
        cursor.execute(query, (correo,))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            conn.close()
            logger.warning("Login fallido: correo no registrado (%s)", correo)
            return None

        id_usuario, nombre, estado_vigencia, rol, password_hash = user
        valido, nuevo_hash = verify_or_upgrade(password, password_hash)
        if valido:
            if nuevo_hash:
                cursor.execute(
                    "UPDATE usuario SET password_hash = %s WHERE id_usuario = %s",
                    (nuevo_hash, id_usuario),
                )
            # H-01: un login exitoso de un usuario vigente cuenta como actividad.
            # Un usuario dado de baja no debe "revivir" por intentar entrar.
            if estado_vigencia:
                marcar_actividad(cursor, id_usuario)
            conn.commit()

        cursor.close()
        conn.close()

        if not valido:
            logger.warning("Login fallido: contraseña incorrecta (%s)", correo)
            return None
        logger.info("Login exitoso: usuario %s (%s)", id_usuario, rol)
        return (id_usuario, nombre, estado_vigencia, rol)
    except Exception as e:
        logger.exception("Error al ejecutar la consulta de login")
        st.error(f"Error en la ejecución de la consulta: {e}")
        return None

def show_login():
    st.markdown("<h2 style='text-align: center;'>SETESA</h2>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>Plataforma de Gestión de Ausencias y Vigencia</h4>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            email = st.text_input("Correo Institucional")
            password = st.text_input("Contraseña", type="password")
            submit_button = st.form_submit_button("Iniciar Sesión", width="stretch")
            
            if submit_button:
                user_data = login_user(email, password)
                
                if user_data:
                    id_usuario, nombre, estado_vigencia, rol = user_data
                    
                    if not estado_vigencia:
                        logger.warning(
                            "Login rechazado: usuario %s inactivo", id_usuario
                        )
                        st.error("Acceso denegado: Usuario inactivo (Baja Lógica).")
                    else:
                        st.session_state['logged_in'] = True
                        st.session_state['id_usuario'] = id_usuario
                        st.session_state['nombre'] = nombre
                        st.session_state['rol'] = rol

                        # V-07: verificación semestral automática al entrar Gerencia.
                        if rol == "Administrador":
                            try:
                                resultado = ejecutar_si_corresponde(id_usuario)
                                if resultado and resultado[0] > 0:
                                    st.session_state["flash_gerencia"] = (
                                        "warning",
                                        f"Depuración automática semestral: "
                                        f"{resultado[0]} usuario(s) dados de baja.",
                                    )
                            except Exception as e:
                                st.session_state["flash_gerencia"] = (
                                    "warning",
                                    f"No se pudo ejecutar la vigencia automática: {e}",
                                )

                        st.success(f"Bienvenido {nombre}.")
                        st.rerun()
                else:
                    st.error("Credenciales incorrectas o usuario no encontrado.")