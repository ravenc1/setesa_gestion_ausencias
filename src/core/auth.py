# Validación de sesión y Control de Acceso Basado en Roles.

import streamlit as st
from src.core.database import get_connection
from src.core.logging_config import obtener_logger
from src.core import intentos, sesion
from src.core.security import hash_password, verify_or_upgrade, verify_password
from src.core.vigencia import ejecutar_si_corresponde, marcar_actividad

logger = obtener_logger("setesa.auth")

# Hash de relleno: se verifica cuando el correo no existe para que la respuesta
# tarde lo mismo que con un correo real (no revela qué correos están registrados).
_HASH_RELLENO = hash_password("relleno-no-valido")


def login_user(email, password):
    """Valida el acceso. Devuelve los datos del usuario o None si falla.

    Lanza CuentaBloqueada si el correo acumuló demasiados intentos fallidos
    (Fase 20); mientras dura el bloqueo ni la contraseña correcta sirve.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        # A-05: el correo se normaliza para evitar fallos por mayúsculas/espacios.
        correo = intentos.normalizar(email)

        minutos = intentos.minutos_restantes(cursor, correo)
        if minutos:
            logger.warning("Login rechazado: acceso bloqueado (%s)", correo)
            raise intentos.CuentaBloqueada(minutos)

        query = """
            SELECT u.id_usuario, u.nombre_completo, u.estado_vigencia, r.nombre_rol, u.password_hash
            FROM usuario u
            JOIN rol r ON u.id_rol = r.id_rol
            WHERE LOWER(u.correo_institucional) = %s
        """
        cursor.execute(query, (correo,))
        user = cursor.fetchone()
        if not user:
            verify_password(password or "", _HASH_RELLENO)
            intentos.registrar_fallo(cursor, correo)
            conn.commit()
            cursor.close()
            conn.close()
            logger.warning("Login fallido: correo no registrado (%s)", correo)
            return None

        id_usuario, nombre, estado_vigencia, rol, password_hash = user
        valido, nuevo_hash = verify_or_upgrade(password, password_hash)
        if valido:
            intentos.limpiar(cursor, correo)
            if nuevo_hash:
                cursor.execute(
                    "UPDATE usuario SET password_hash = %s WHERE id_usuario = %s",
                    (nuevo_hash, id_usuario),
                )
            # H-01: un login exitoso de un usuario vigente cuenta como actividad.
            # Un usuario dado de baja no debe "revivir" por intentar entrar.
            if estado_vigencia:
                marcar_actividad(cursor, id_usuario)
                # Fase 13: si llevaba más de 6 meses sin actualizar sus datos,
                # el trigger trg_usuario_vigencia acaba de aplicarle la baja.
                cursor.execute(
                    "SELECT estado_vigencia FROM usuario WHERE id_usuario = %s",
                    (id_usuario,),
                )
                estado_vigencia = cursor.fetchone()[0]
        else:
            intentos.registrar_fallo(cursor, correo)
        conn.commit()

        cursor.close()
        conn.close()

        if not valido:
            logger.warning("Login fallido: contraseña incorrecta (%s)", correo)
            return None
        logger.info("Login exitoso: usuario %s (%s)", id_usuario, rol)
        return (id_usuario, nombre, estado_vigencia, rol)
    except intentos.CuentaBloqueada:
        conn.close()
        raise
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
            email = st.text_input(
                "Correo registrado",
                help=(
                    "Correo con el que IT registró su cuenta. Puede ser de "
                    "SETESA, del banco o personal."
                ),
            )
            password = st.text_input("Contraseña", type="password")
            submit_button = st.form_submit_button("Iniciar Sesión", width="stretch")
            
            if submit_button:
                try:
                    user_data = login_user(email, password)
                except intentos.CuentaBloqueada as e:
                    st.error(f"🔒 {e}")
                    return
                
                if user_data:
                    id_usuario, nombre, estado_vigencia, rol = user_data
                    
                    if not estado_vigencia:
                        logger.warning(
                            "Login rechazado: usuario %s inactivo", id_usuario
                        )
                        st.error("Acceso denegado: Usuario inactivo (Baja Lógica).")
                    else:
                        sesion.iniciar(st.session_state)
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
                    st.error(
                        "Credenciales incorrectas. Tras "
                        f"{intentos.MAX_INTENTOS} intentos fallidos el acceso se "
                        f"bloquea {intentos.MINUTOS_BLOQUEO} minutos."
                    )