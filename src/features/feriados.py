# Panel de administración del catálogo de feriados (D-04 / RF-01).

import datetime

import streamlit as st

from src.core.feriados import (
    FeriadoError,
    crear_feriado,
    eliminar_feriado,
    listar_feriados,
)
from src.core.security import rol_autorizado


def mostrar_panel_feriados():
    if not rol_autorizado(["Administrador"]):
        st.error("Acceso denegado: esta sección es exclusiva del rol Administrador.")
        return

    st.markdown("### 🗓️ Catálogo de Feriados")
    st.info(
        "Los feriados de este catálogo se excluyen del cálculo de días hábiles "
        "de las solicitudes (RF-01)."
    )

    hoy = datetime.date.today()
    anios = list(range(hoy.year - 1, hoy.year + 3))
    anio = st.selectbox("Año a consultar", anios, index=1)

    df_feriados = listar_feriados(anio)
    if df_feriados.empty:
        st.warning(f"No hay feriados registrados para {anio}.")
    else:
        st.dataframe(df_feriados, hide_index=True, width="stretch")
        st.caption(f"{len(df_feriados)} feriado(s) registrados en {anio}.")

    st.write("---")
    st.markdown("#### ➕ Agregar o actualizar un feriado")
    with st.form("form_nuevo_feriado", clear_on_submit=True):
        col_fecha, col_nombre = st.columns([1, 2])
        with col_fecha:
            fecha = st.date_input("Fecha", value=hoy)
        with col_nombre:
            nombre = st.text_input("Nombre del feriado")
        guardar = st.form_submit_button("Guardar feriado", type="primary")

    if guardar:
        try:
            crear_feriado(fecha, nombre)
        except FeriadoError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"No se pudo guardar el feriado: {e}")
        else:
            st.success(f"Feriado del {fecha.isoformat()} guardado.")
            st.rerun()

    if not df_feriados.empty:
        st.write("---")
        st.markdown("#### 🗑️ Eliminar un feriado")
        opciones = {
            f"#{fila.id_feriado} · {fila.fecha} · {fila.nombre}": fila.id_feriado
            for fila in df_feriados.itertuples()
        }
        seleccion = st.selectbox("Feriado a eliminar", list(opciones))
        if st.button("Eliminar feriado seleccionado"):
            try:
                eliminado = eliminar_feriado(opciones[seleccion])
            except FeriadoError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"No se pudo eliminar el feriado: {e}")
            else:
                if eliminado:
                    st.success("Feriado eliminado.")
                    st.rerun()
                else:
                    st.warning("El feriado ya no existía.")
