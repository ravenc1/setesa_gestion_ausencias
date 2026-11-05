# Pantalla "Mis datos" y aviso de actualización semestral (Fase 14).

import streamlit as st

from src.core.perfil import (
    CAMPOS_POR_ROL,
    PerfilError,
    actualizar_mis_datos,
    en_periodo_de_aviso,
    obtener_perfil,
)
from src.core.security import rol_autorizado
from src.core.vigencia import DIAS_AVISO, ROLES_CON_ACTUALIZACION


def mostrar_aviso_actualizacion():
    """Aviso en cada pantalla desde 30 días antes del vencimiento."""
    if st.session_state.get("rol") not in ROLES_CON_ACTUALIZACION:
        return
    try:
        perfil = obtener_perfil(st.session_state.get("id_usuario"))
    except Exception:
        return
    if not perfil or not en_periodo_de_aviso(perfil["fecha_actualizacion_datos"]):
        return
    restantes = perfil["dias_restantes"]
    limite = f"{perfil['fecha_limite']:%d/%m/%Y}"
    if restantes <= 0:
        texto = f"hoy ({limite}) vence el plazo"
    else:
        texto = f"le quedan {restantes} día(s): el plazo vence el {limite}"
    st.warning(
        f"🔔 Actualice sus datos en **Mis datos**: {texto}. Si no los "
        "actualiza, su cuenta pasará a baja lógica."
    )


def mostrar_mis_datos():
    if not rol_autorizado(list(ROLES_CON_ACTUALIZACION)):
        st.error("Esta sección es solo para Consultor y Contabilidad y RR.HH.")
        return

    st.markdown("### 👤 Mis datos")
    flash = st.session_state.pop("flash_mis_datos", None)
    if flash:
        st.success(flash)

    perfil = obtener_perfil(st.session_state.get("id_usuario"))
    if not perfil:
        st.error("No se pudieron cargar sus datos.")
        return

    st.info(
        "Por política de SETESA, confirme o actualice sus datos al menos cada "
        "6 meses para mantener su cuenta activa. Cada confirmación renueva el "
        f"plazo por 6 meses más; el aviso aparece {DIAS_AVISO} días antes. "
        "Para cambiar su nombre o correo, comuníquese con IT."
    )

    col_a, col_b = st.columns(2)
    col_a.metric(
        "Plazo para actualizar",
        f"{perfil['fecha_limite']:%d/%m/%Y}" if perfil["fecha_limite"] else "—",
    )
    col_b.metric("Días restantes", perfil["dias_restantes"])
    if perfil["fecha_actualizacion_datos"]:
        st.caption(
            "Última actualización: "
            f"{perfil['fecha_actualizacion_datos']:%d/%m/%Y %H:%M}."
        )

    campos = CAMPOS_POR_ROL[perfil["nombre_rol"]]
    with st.form("form_mis_datos"):
        st.text_input("Nombre", perfil["nombre_completo"], disabled=True)
        st.text_input(
            "Correo registrado", perfil["correo_institucional"], disabled=True
        )
        puesto = st.text_input("Puesto", perfil["puesto"])
        codigo = None
        if "codigo_empleado" in campos:
            codigo = st.text_input("Código de empleado", perfil["codigo_empleado"])
        telefono = st.text_input("Teléfono de contacto", perfil["telefono"])
        guardar = st.form_submit_button(
            "✅ Confirmar y actualizar mis datos", type="primary"
        )

    if guardar:
        try:
            limite = actualizar_mis_datos(
                st.session_state["id_usuario"], puesto, codigo, telefono
            )
        except PerfilError as e:
            st.error(f"❌ {e}")
        except Exception as e:
            st.error(f"No se pudieron guardar sus datos: {e}")
        else:
            st.session_state["flash_mis_datos"] = (
                "Datos actualizados. Su próximo plazo vence el "
                f"{limite:%d/%m/%Y}."
            )
            st.rerun()
