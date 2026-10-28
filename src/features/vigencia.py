# Panel de auditoría y vigencia de usuarios (RF-05 / CU-06 / QA-06).
#
# La lógica vive en src/core/vigencia.py; este módulo solo compone la interfaz.

import streamlit as st

from src.core.security import rol_autorizado
from src.core.vigencia import (
    ROLES_PROTEGIDOS,
    UsuarioNoEncontrado,
    ejecutar_depuracion,
    obtener_dados_de_baja,
    obtener_historial_vigencia,
    obtener_inactivos,
    reactivar_usuario,
)


def _mostrar_tabla(df, vacio):
    if df.empty:
        st.info(vacio)
    else:
        st.dataframe(df, hide_index=True, width="stretch")


def mostrar_panel_vigencia():
    if not rol_autorizado(["Administrador"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Administrador.")
        return

    st.markdown("### 🛡️ Módulo de Auditoría y Vigencia de Usuarios")
    flash = st.session_state.pop("flash_vigencia", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.info(
        "El algoritmo aplica baja lógica a los usuarios con más de 6 meses sin "
        "actividad, sin borrar su historial. Los roles administrativos "
        f"({', '.join(ROLES_PROTEGIDOS)}) están protegidos y nunca se "
        "desactivan automáticamente."
    )

    id_ejecutor = st.session_state.get("id_usuario")

    # 1. Candidatos a baja (vista previa, no modifica nada)
    st.markdown("#### 🔎 Candidatos a baja lógica")
    df_candidatos = obtener_inactivos(id_excluido=id_ejecutor)
    _mostrar_tabla(
        df_candidatos,
        "No hay usuarios activos con más de 6 meses de inactividad.",
    )

    # 2. Ejecución manual
    st.write("---")
    st.markdown("#### ⚙️ Ejecución del algoritmo")
    st.caption(
        "También se ejecuta automáticamente al iniciar sesión Gerencia si han "
        "pasado 6 meses desde la última depuración."
    )
    if st.button(
        "Ejecutar Algoritmo de Depuración", width="stretch", type="primary"
    ):
        try:
            df_afectados, _ = ejecutar_depuracion(id_ejecutor=id_ejecutor)
        except Exception as e:
            st.error(f"Error al ejecutar el algoritmo de vigencia: {e}")
        else:
            if df_afectados.empty:
                st.info(
                    "Escaneo completado. No se encontraron usuarios con más de "
                    "6 meses de inactividad."
                )
            else:
                st.success(
                    f"Depuración exitosa: {len(df_afectados)} usuario(s) dados "
                    "de baja lógica."
                )
                st.dataframe(df_afectados, hide_index=True, width="stretch")

    # 3. Usuarios actualmente dados de baja + reactivación
    st.write("---")
    st.markdown("#### ♻️ Reactivación de usuarios")
    df_baja = obtener_dados_de_baja()
    _mostrar_tabla(df_baja, "No hay usuarios dados de baja.")

    if not df_baja.empty:
        with st.form("form_reactivacion"):
            id_reactivar = st.selectbox(
                "Usuario a reactivar:",
                df_baja["id_usuario"].tolist(),
                format_func=lambda valor: (
                    f"#{valor} · "
                    f"{df_baja.loc[df_baja['id_usuario'] == valor, 'nombre_completo'].iloc[0]}"
                ),
            )
            confirmar = st.form_submit_button(
                "Reactivar usuario y actualizar actividad", type="primary"
            )

        if confirmar and id_reactivar:
            try:
                reactivar_usuario(id_reactivar, id_ejecutor=id_ejecutor)
            except UsuarioNoEncontrado as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"No se pudo reactivar el usuario: {e}")
            else:
                st.session_state["flash_vigencia"] = (
                    "success",
                    f"El usuario #{id_reactivar} fue reactivado.",
                )
                st.rerun()

    # 4. Auditoría
    st.write("---")
    st.markdown("#### 🕓 Historial de ejecuciones")
    df_log = obtener_historial_vigencia()
    _mostrar_tabla(df_log, "Aún no hay ejecuciones registradas.")
