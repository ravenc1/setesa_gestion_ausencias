# Panel de gestión de usuarios (Fase 9).
#
# Solo el rol IT accede. La lógica y las validaciones viven en
# src/core/gestion_usuarios.py; este módulo solo compone la interfaz.

import streamlit as st

from src.core.gestion_usuarios import (
    CorreoDuplicado,
    DatosInvalidos,
    GestionUsuariosError,
    OperacionNoPermitida,
    cambiar_estado_usuario,
    crear_usuario,
    editar_usuario,
    listar_auditoria,
    listar_roles,
    listar_usuarios,
    resetear_password,
)
from src.core.avisos import ultimos_avisos
from src.core.recordatorios import construir_enlace_correo
from src.core.reasignacion import contar_pendientes_coordinador
from src.core.vigencia import DIAS_AVISO, obtener_por_vencer
from src.features.reasignacion import mostrar_panel_reasignacion
from src.core.security import ROL_IT, nombre_rol_visible, rol_autorizado

COLUMNAS_USUARIOS = {
    "id_usuario": "ID",
    "nombre_completo": "Nombre",
    "correo_institucional": "Correo registrado",
    "nombre_rol": "Rol",
    "estado_vigencia": "Activo",
    "ultima_actividad": "Última actividad",
    "fecha_limite_datos": "Actualizar datos antes de",
    "dias_vacaciones_asignados": "Días asignados",
    "dias_usados": "Días usados",
    "dias_disponibles": "Días disponibles",
}

COLUMNAS_AUDITORIA = {
    "id_log": "ID",
    "fecha": "Fecha",
    "ejecutor": "Ejecutor",
    "afectado": "Afectado",
    "accion": "Acción",
    "detalle": "Detalle",
}


def _flash(tipo, texto):
    st.session_state["flash_usuarios"] = (tipo, texto)


def _mostrar_flash():
    flash = st.session_state.pop("flash_usuarios", None)
    if flash:
        getattr(st, flash[0])(flash[1])


def _etiqueta_usuario(fila):
    estado = "Activo" if fila["estado_vigencia"] else "Inactivo"
    return (
        f"#{fila['id_usuario']} · {fila['nombre_completo']} · "
        f"{nombre_rol_visible(fila['nombre_rol'])} · {estado}"
    )


def _indice_rol(roles, nombre_rol):
    nombres = roles["nombre_rol"].tolist()
    return nombres.index(nombre_rol) if nombre_rol in nombres else 0


def _mostrar_tabla_usuarios(df):
    tabla = df.rename(columns=COLUMNAS_USUARIOS).copy()
    tabla["Activo"] = tabla["Activo"].map({True: "Sí", False: "No"})
    st.dataframe(tabla, hide_index=True, width="stretch")


def _formulario_edicion(fila, roles):
    id_usuario = int(fila["id_usuario"])
    es_yo = id_usuario == st.session_state.get("id_usuario")

    st.markdown("#### ✏️ Editar datos")
    if es_yo:
        st.caption("Está editando su propia cuenta: no puede cambiar su rol.")

    with st.form(f"form_editar_{id_usuario}"):
        nombre = st.text_input(
            "Nombre completo",
            value=fila["nombre_completo"],
            key=f"editar_nombre_{id_usuario}",
        )
        correo = st.text_input(
            "Correo registrado",
            value=fila["correo_institucional"],
            key=f"editar_correo_{id_usuario}",
            help="Puede ser de SETESA, del banco o personal.",
        )
        rol = st.selectbox(
            "Rol",
            roles["nombre_rol"].tolist(),
            index=_indice_rol(roles, fila["nombre_rol"]),
            format_func=nombre_rol_visible,
            key=f"editar_rol_{id_usuario}",
            disabled=es_yo,
        )
        dias = st.number_input(
            "Días de vacaciones asignados",
            min_value=0,
            max_value=365,
            value=int(fila["dias_vacaciones_asignados"]),
            step=1,
            key=f"editar_dias_{id_usuario}",
        )
        guardar = st.form_submit_button("💾 Guardar cambios")

    if guardar:
        try:
            editar_usuario(
                st.session_state["id_usuario"],
                id_usuario,
                nombre,
                correo,
                rol,
                dias,
            )
        except (DatosInvalidos, CorreoDuplicado, OperacionNoPermitida) as e:
            st.error(f"⚠️ {e}")
        except GestionUsuariosError as e:
            st.error(f"No se pudo guardar: {e}")
        else:
            if es_yo:
                # Mantiene el saludo del sidebar al día tras editar la propia cuenta.
                st.session_state["nombre"] = nombre
            _flash("success", f"Datos de {nombre} actualizados.")
            st.rerun()


def _acciones_acceso(fila):
    id_usuario = int(fila["id_usuario"])
    es_yo = id_usuario == st.session_state.get("id_usuario")
    activo = bool(fila["estado_vigencia"])

    st.markdown("#### 🔐 Acceso y contraseña")
    col_estado, col_clave = st.columns(2)

    with col_estado:
        if activo:
            if st.button(
                "🚫 Dar de baja",
                key=f"baja_{id_usuario}",
                disabled=es_yo,
                help="No puede desactivar su propia cuenta.",
            ):
                try:
                    cambiar_estado_usuario(
                        st.session_state["id_usuario"], id_usuario, False
                    )
                except (OperacionNoPermitida, GestionUsuariosError) as e:
                    st.error(f"⚠️ {e}")
                else:
                    aviso = f"{fila['nombre_completo']} quedó dado de baja."
                    # Fase 12: sus expedientes sin firmar quedan detenidos.
                    if fila["nombre_rol"] == "Coordinador GTC":
                        pendientes = contar_pendientes_coordinador(id_usuario)
                        if pendientes:
                            aviso += (
                                f" Tenía {pendientes} expediente(s) esperando "
                                "su visto bueno: reasígnelos en la pestaña "
                                "«Reasignar Coordinador»."
                            )
                    _flash("warning", aviso)
                    st.rerun()
        else:
            if st.button("✅ Reactivar", key=f"reactivar_{id_usuario}"):
                try:
                    cambiar_estado_usuario(
                        st.session_state["id_usuario"], id_usuario, True
                    )
                except (OperacionNoPermitida, GestionUsuariosError) as e:
                    st.error(f"⚠️ {e}")
                else:
                    _flash("success", f"{fila['nombre_completo']} fue reactivado.")
                    st.rerun()

    with col_clave:
        with st.form(f"form_reset_{id_usuario}"):
            nueva = st.text_input(
                "Nueva contraseña",
                type="password",
                key=f"reset_nueva_{id_usuario}",
            )
            confirmar = st.text_input(
                "Confirmar contraseña",
                type="password",
                key=f"reset_confirmar_{id_usuario}",
            )
            restablecer = st.form_submit_button("🔑 Restablecer contraseña")

        if restablecer:
            if nueva != confirmar:
                st.error("Las contraseñas no coinciden.")
            else:
                try:
                    resetear_password(
                        st.session_state["id_usuario"], id_usuario, nueva
                    )
                except (DatosInvalidos, GestionUsuariosError) as e:
                    st.error(f"⚠️ {e}")
                else:
                    _flash(
                        "success",
                        f"Contraseña de {fila['nombre_completo']} restablecida.",
                    )
                    st.rerun()


def _tab_usuarios(df, roles):
    if df.empty:
        st.info("No hay usuarios registrados.")
        return

    _mostrar_tabla_usuarios(df)
    st.write("---")

    opciones = df["id_usuario"].tolist()
    id_seleccionado = st.selectbox(
        "Seleccione un usuario para administrar",
        opciones,
        format_func=lambda valor: _etiqueta_usuario(
            df[df["id_usuario"] == valor].iloc[0]
        ),
    )
    fila = df[df["id_usuario"] == id_seleccionado].iloc[0]

    _formulario_edicion(fila, roles)
    st.write("---")
    _acciones_acceso(fila)


def _tab_crear(roles):
    st.markdown("#### ➕ Nueva cuenta")
    st.caption(
        "El correo registrado es el identificador de acceso y el destino de los "
        "recordatorios. Puede ser de SETESA, del banco o personal."
    )
    with st.form("form_crear_usuario"):
        nombre = st.text_input("Nombre completo", key="crear_nombre")
        correo = st.text_input("Correo registrado", key="crear_correo")
        rol = st.selectbox(
            "Rol",
            roles["nombre_rol"].tolist(),
            key="crear_rol",
            format_func=nombre_rol_visible,
        )
        dias = st.number_input(
            "Días de vacaciones asignados",
            min_value=0,
            max_value=365,
            value=15,
            step=1,
            key="crear_dias",
        )
        password = st.text_input(
            "Contraseña inicial",
            type="password",
            key="crear_password",
            help="Mínimo 8 caracteres, con al menos una letra y un número.",
        )
        confirmar = st.text_input(
            "Confirmar contraseña", type="password", key="crear_confirmar"
        )
        crear = st.form_submit_button("➕ Crear usuario", type="primary")

    if crear:
        if password != confirmar:
            st.error("Las contraseñas no coinciden.")
            return
        try:
            id_nuevo = crear_usuario(
                st.session_state["id_usuario"],
                nombre,
                correo,
                rol,
                password,
                dias,
            )
        except (DatosInvalidos, CorreoDuplicado, OperacionNoPermitida) as e:
            st.error(f"⚠️ {e}")
        except GestionUsuariosError as e:
            st.error(f"No se pudo crear el usuario: {e}")
        else:
            _flash("success", f"Usuario creado con id {id_nuevo}.")
            st.rerun()


def _tab_auditoria():
    st.markdown("#### 🧾 Últimas acciones de gestión")
    st.caption(
        "Se registran altas, ediciones, bajas, reactivaciones y reseteos de "
        "contraseña, con el ejecutor y el usuario afectado."
    )
    df = listar_auditoria()
    if df.empty:
        st.info("Aún no hay acciones registradas.")
        return
    st.dataframe(
        df.rename(columns=COLUMNAS_AUDITORIA),
        hide_index=True,
        width="stretch",
    )


def _tab_por_vencer():
    """Usuarios que deben actualizar sus datos en los próximos 30 días."""
    st.markdown(f"#### ⏳ Actualización de datos por vencer ({DIAS_AVISO} días)")
    st.caption(
        "Consultor y Contabilidad y RR.HH. deben actualizar sus datos cada "
        "6 meses en «Mis datos»; si no lo hacen, pasan a baja lógica."
    )
    df = obtener_por_vencer()
    if df.empty:
        st.info("Ningún usuario tiene su plazo por vencer.")
    else:
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption(
            "Además del aviso dentro del sistema, la tarea diaria les envía un "
            "correo 30, 15, 7 y 1 día(s) antes del vencimiento. Los enlaces de "
            "abajo permiten escribirles manualmente."
        )

    st.markdown("#### ✉️ Últimos correos de recordatorio")
    try:
        df_avisos = ultimos_avisos()
    except Exception:
        df_avisos = None
    if df_avisos is None or df_avisos.empty:
        st.info("Aún no se han enviado correos de recordatorio.")
    else:
        st.dataframe(df_avisos, hide_index=True, width="stretch")

    if df.empty:
        return
    st.markdown("#### 📨 Escribir manualmente")
    for fila in df.itertuples():
        enlace = construir_enlace_correo(
            fila.correo_institucional,
            "SETESA: actualice sus datos en el sistema de ausencias",
            f"Estimado(a) {fila.nombre_completo}: su plazo para actualizar "
            f"sus datos vence el {fila.fecha_limite:%d/%m/%Y}. Ingrese al "
            "sistema, abra «Mis datos» y confirme su información para "
            "mantener su cuenta activa.",
        )
        st.markdown(f"- [✉️ Recordar a {fila.nombre_completo}]({enlace})")


def mostrar_panel_usuarios():
    if not rol_autorizado([ROL_IT]):
        st.error("Acceso denegado: esta sección es exclusiva del rol IT.")
        return

    st.markdown("### 👥 Gestión de Usuarios")
    _mostrar_flash()
    st.info(
        "Desde aquí se crean y administran las cuentas. El rol determina el "
        "panel al que accede cada persona; no existe autorregistro."
    )

    roles = listar_roles()
    if roles.empty:
        st.error("No se pudieron cargar los roles del sistema.")
        return

    df = listar_usuarios()
    tab_usuarios, tab_crear, tab_reasignar, tab_vencer, tab_auditoria = st.tabs(
        [
            "👥 Usuarios",
            "➕ Crear usuario",
            "🔁 Reasignar Coordinador",
            "⏳ Por vencer",
            "🧾 Auditoría",
        ]
    )
    with tab_usuarios:
        _tab_usuarios(df, roles)
    with tab_crear:
        _tab_crear(roles)
    with tab_reasignar:
        # IT da de baja al coordinador saliente y reasigna sus expedientes.
        mostrar_panel_reasignacion()
    with tab_vencer:
        _tab_por_vencer()
    with tab_auditoria:
        _tab_auditoria()
