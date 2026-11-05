# Trazabilidad, filtros y descargas del panel gerencial (RF-04 / HU-03).


import pandas as pd
import streamlit as st

from src.core.cache import lectura
from src.core.database import get_engine
from src.core.indicadores import (
    calcular_tiempos,
    formatear_duracion,
    obtener_tiempos_resolucion,
    obtener_usuarios,
    resumen_usuarios,
)
from src.core.logging_config import obtener_logger
from src.core.reportes import (
    calcular_kpis,
    exportar_csv,
    filtrar_solicitudes,
    nombre_archivo_csv,
    resumen_por_tipo,
)
from src.core.security import ROLES_PANEL, es_solo_lectura, rol_autorizado
from src.core.solicitudes import (
    FirmaRequerida,
    MotivoRequerido,
    NoAutorizadoParaDenegar,
    TransicionInvalida,
    cambiar_estado,
    denegar_solicitud,
    obtener_historial,
)
from src.core.workflow import (
    ESTADOS_WORKFLOW,
    ESTADO_FINALIZADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
)
from src.services.documentos import (
    generar_pdf_solicitud,
    obtener_pdf_final_verificado,
)
from src.features.evidencias import mostrar_evidencias
from src.services.utils_firma import canvas_to_base64
from src.core.motivos import listar_motivos
from src.core.usuarios import listar_colaboradores
from src.ui.estilos import colorear_estados

logger = obtener_logger("setesa.dashboard")


@lectura(ttl=15)
def _leer_solicitudes():
    """Lectura guardada unos segundos; si falla, lanza (los errores no se guardan)."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()

    query = """
        SELECT s.id_solicitud, s.id_usuario, u.nombre_completo, s.tipo_ausencia,
               s.fecha_inicio, s.fecha_fin, s.dias_solicitados,
               s.estado_workflow, s.resolucion, s.fecha_creacion,
               s.ruta_pdf, s.pdf_hash
        FROM solicitud s
        JOIN usuario u ON s.id_usuario = u.id_usuario
        ORDER BY s.fecha_creacion DESC
    """
    return pd.read_sql_query(query, engine)


def obtener_solicitudes():
    """Recupera todas las solicitudes con el nombre del colaborador."""
    try:
        return _leer_solicitudes()
    except Exception as e:
        logger.exception("Error al obtener las solicitudes del dashboard")
        st.error(f"Error al obtener solicitudes: {e}")
        return pd.DataFrame()


def _etiqueta_solicitud(df, id_solicitud):
    fila = df.loc[df["id_solicitud"] == id_solicitud].iloc[0]
    return f"#{id_solicitud} · {fila['nombre_completo']} · {fila['tipo_ausencia']}"


def _mostrar_alertas(kpis):
    pendientes = []
    if kpis["pendientes_coordinador"]:
        pendientes.append(
            f"{kpis['pendientes_coordinador']} pendiente(s) de firma del "
            "Coordinador GTC"
        )
    if kpis["pendientes_gerencia"]:
        pendientes.append(
            f"{kpis['pendientes_gerencia']} pendiente(s) de aprobación de "
            "Gerencia"
        )

    if pendientes:
        st.warning("🔔 " + "; ".join(pendientes) + ".")
    else:
        st.success("No hay expedientes pendientes de firma en este momento.")


def _mostrar_kpis(kpis):
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total de Expedientes", kpis["total"])
    col2.metric("Ingresadas", kpis["ingresadas"])
    col3.metric("Pendientes Coordinador", kpis["pendientes_coordinador"])
    col4.metric("Pendientes Gerencia", kpis["pendientes_gerencia"])
    col5.metric(
        "Finalizadas",
        kpis["finalizadas"],
        help=(
            f"Aprobadas: {kpis['aprobadas']} · Denegadas: {kpis['denegadas']} · "
            f"Retiradas: {kpis['retiradas']}"
        ),
    )
    st.caption(
        f"Resoluciones: ✅ {kpis['aprobadas']} aprobada(s) · "
        f"⛔ {kpis['denegadas']} denegada(s)."
    )


def _opciones_colaborador():
    """{etiqueta: (id_usuario, vigente)} con todos los consultores registrados."""
    opciones = {"Todos": (None, True)}
    try:
        colaboradores = listar_colaboradores()
    except Exception as e:
        logger.warning("No se pudo cargar la lista de colaboradores: %s", e)
        return opciones
    repetidos = colaboradores["nombre_completo"].duplicated(keep=False)
    for fila, repetido in zip(colaboradores.itertuples(), repetidos):
        etiqueta = fila.nombre_completo
        if repetido:
            etiqueta += f" (#{fila.id_usuario})"
        if not fila.vigente:
            etiqueta += " — inactivo"
        opciones[etiqueta] = (int(fila.id_usuario), bool(fila.vigente))
    return opciones


def _opciones_tipo(df_solicitudes):
    """Todos los motivos del catálogo (y los que ya figuren en expedientes)."""
    try:
        catalogo = listar_motivos()["nombre"].tolist()
    except Exception as e:
        logger.warning("No se pudo cargar el catálogo de motivos: %s", e)
        catalogo = []
    usados = df_solicitudes["tipo_ausencia"].dropna().astype(str).unique().tolist()
    return ["Todos"] + catalogo + sorted(t for t in usados if t not in catalogo)


def _mostrar_indicadores_usuarios():
    """Usuarios vigentes e inactivos (tesis: porcentaje de usuarios inactivos)."""
    try:
        resumen = resumen_usuarios(obtener_usuarios())
    except Exception as e:
        logger.warning("No se pudieron calcular los indicadores de usuarios: %s", e)
        return
    if not resumen["total"]:
        return
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Usuarios vigentes", resumen["vigentes"])
    col2.metric("Usuarios inactivos", resumen["inactivos"])
    col3.metric("% de inactivos", f"{resumen['pct_inactivos']}%")
    col4.metric(
        "Por vencer (30 días)",
        resumen["por_vencer"],
        help="Consultores y Contabilidad que deben actualizar «Mis datos».",
    )


def _mostrar_tiempos():
    """Tiempo promedio de aprobación, total y por etapa."""
    try:
        tiempos = calcular_tiempos(obtener_tiempos_resolucion())
    except Exception as e:
        logger.warning("No se pudieron calcular los tiempos de aprobación: %s", e)
        return
    if not tiempos["resueltas"]:
        st.caption("⏱️ Aún no hay expedientes resueltos para calcular tiempos.")
        return
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "⏱️ Tiempo promedio de aprobación",
        formatear_duracion(tiempos["total"]),
        help=f"De la solicitud a su resolución; {tiempos['resueltas']} expediente(s) resuelto(s).",
    )
    col2.metric("Hasta el visto bueno del banco", formatear_duracion(tiempos["banco"]))
    col3.metric("Etapa de Gerencia", formatear_duracion(tiempos["gerencia"]))
    st.caption(
        f"Aprobadas: {formatear_duracion(tiempos['aprobadas'])} · "
        f"Denegadas: {formatear_duracion(tiempos['denegadas'])}."
    )


def _mostrar_tabla(df_filtrado):
    if df_filtrado.empty:
        st.info("No hay expedientes que coincidan con los filtros seleccionados.")
        return

    col_pagina, col_tamano = st.columns(2)
    with col_tamano:
        tam_pagina = st.selectbox("Filas por página", [10, 25, 50, 100], index=0)
    paginas = max(1, (len(df_filtrado) + tam_pagina - 1) // tam_pagina)
    with col_pagina:
        pagina = st.selectbox("Página", list(range(1, paginas + 1)))

    inicio = (pagina - 1) * tam_pagina
    vista = df_filtrado.iloc[inicio : inicio + tam_pagina].drop(
        columns=["ruta_pdf", "id_usuario"], errors="ignore"
    )
    if "resolucion" in vista:
        vista = vista.assign(resolucion=vista["resolucion"].fillna("—"))
    st.dataframe(colorear_estados(vista), width="stretch", hide_index=True)
    st.caption(
        f"Mostrando {len(vista)} de {len(df_filtrado)} expedientes filtrados."
    )


@st.cache_resource(ttl=600, max_entries=16, show_spinner=False)
def _pdf_final(id_solicitud):
    """PDF final verificado; es inmutable, por eso se guarda 10 minutos."""
    return obtener_pdf_final_verificado(id_solicitud)


def _mostrar_descargas(df_filtrado):
    st.write("---")
    st.markdown("#### 📥 Descarga del expediente final (HU-03)")

    col_pdf, col_csv = st.columns(2)

    with col_pdf:
        finalizadas = df_filtrado[
            df_filtrado["estado_workflow"] == ESTADO_FINALIZADA
        ]
        if finalizadas.empty:
            st.info("No hay expedientes finalizados en la selección actual.")
        else:
            id_pdf = st.selectbox(
                "Expediente finalizado:",
                finalizadas["id_solicitud"].tolist(),
                format_func=lambda valor: _etiqueta_solicitud(finalizadas, valor),
            )
            try:
                nombre_pdf, contenido, integridad = _pdf_final(int(id_pdf))
            except Exception as e:
                logger.exception("No se pudo preparar el PDF final %s", id_pdf)
                st.error(f"No se pudo preparar el PDF final: {e}")
            else:
                st.download_button(
                    "📥 Descargar PDF final con firmas",
                    data=contenido,
                    file_name=nombre_pdf,
                    mime="application/pdf",
                    type="primary",
                )
                if integridad["estado"] == "ok":
                    st.success("🔐 Integridad verificada (SHA-256).")
                elif integridad["estado"] == "alterado":
                    st.error(
                        "⚠️ El PDF no coincide con el sello registrado: el "
                        "archivo fue alterado. No lo use y repórtelo a IT."
                    )
                elif integridad["estado"] == "sin_sello":
                    st.warning(
                        "El PDF existe pero no tiene sello registrado; "
                        "regenere el documento para sellarlo."
                    )
                else:
                    st.info("El PDF aún no está disponible en el repositorio.")

                with st.expander("Ver sello SHA-256"):
                    st.code(
                        integridad["sello_esperado"] or "Sin sello registrado",
                        language="text",
                    )
                    if integridad["sello_actual"]:
                        st.caption(
                            "Sello calculado del archivo actual: "
                            f"{integridad['sello_actual']}"
                        )

    with col_csv:
        st.caption(
            "El CSV respeta los filtros aplicados y es compatible con Excel."
        )
        st.download_button(
            "📤 Exportar resultados (CSV)",
            data=exportar_csv(df_filtrado),
            file_name=nombre_archivo_csv(),
            mime="text/csv",
        )


def _mostrar_evidencias(df_filtrado):
    """Fase 18: evidencias del expediente (Gerencia y Contabilidad y RR.HH.)."""
    if df_filtrado.empty:
        return
    st.write("---")
    st.markdown("#### 📎 Evidencias del expediente")
    id_ev = st.selectbox(
        "Expediente:",
        df_filtrado["id_solicitud"].tolist(),
        format_func=lambda valor: _etiqueta_solicitud(df_filtrado, valor),
        key="evidencias_expediente",
    )
    mostrar_evidencias(id_ev, st.session_state.get("id_usuario"), "dash")


def _mostrar_trazabilidad(df_filtrado):
    """Historial de estados en modo consulta (rol Contabilidad, HU-03)."""
    st.write("---")
    st.markdown("#### 🕓 Trazabilidad de los expedientes")

    id_seleccionado = st.selectbox(
        "ID de la Solicitud", df_filtrado["id_solicitud"].tolist()
    )
    fila = df_filtrado[df_filtrado["id_solicitud"] == id_seleccionado].iloc[0]
    st.write(f"**Estado actual:** {fila['estado_workflow']}")

    with st.expander(
        f"🕓 Historial de estados del expediente #{id_seleccionado}"
    ):
        df_movimientos = obtener_historial(id_seleccionado)
        if df_movimientos.empty:
            st.info("Sin movimientos registrados.")
        else:
            st.dataframe(df_movimientos, hide_index=True, width="stretch")


def mostrar_dashboard():
    if not rol_autorizado(ROLES_PANEL):
        st.error(
            "Acceso denegado: esta sección es exclusiva de Gerencia y "
            "Contabilidad y RR.HH."
        )
        return

    solo_lectura = es_solo_lectura()
    st.markdown(
        "### Contabilidad y RR.HH. – Repositorio de Expedientes"
        if solo_lectura
        else "### Panel de Control Gerencial y Aprobaciones"
    )
    flash = st.session_state.pop("flash_gerencia", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.info(
        "Repositorio centralizado de solicitudes aprobadas para el proceso de "
        "nómina (HU-03)."
        if solo_lectura
        else "Módulo de trazabilidad y gobernanza sobre las incidencias del "
        "personal externo."
    )

    _mostrar_indicadores_usuarios()

    df_solicitudes = obtener_solicitudes()

    if df_solicitudes.empty:
        st.warning("Aún no hay solicitudes de ausencia registradas en la base de datos.")
        return

    invalidos = df_solicitudes[
        ~df_solicitudes["estado_workflow"].isin(ESTADOS_WORKFLOW)
    ]
    if not invalidos.empty:
        st.warning(
            "Hay solicitudes con estados fuera del catálogo. "
            "Ejecute la migración de datos antes de continuar."
        )
        st.dataframe(invalidos, hide_index=True, width="stretch")

    kpis = calcular_kpis(df_solicitudes)
    _mostrar_alertas(kpis)
    _mostrar_kpis(kpis)
    _mostrar_tiempos()

    st.write("---")
    st.markdown("#### 🔎 Repositorio Histórico y Filtros")

    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        colaboradores = _opciones_colaborador()
        eleccion = st.selectbox("👤 Colaborador", list(colaboradores))
        filtro_id_usuario, colaborador_activo = colaboradores[eleccion]
    with f_col2:
        filtro_estado = st.selectbox(
            "📌 Estado del workflow", ["Todos"] + ESTADOS_WORKFLOW
        )
    with f_col3:
        filtro_tipo = st.selectbox(
            "🏷️ Tipo de incidencia", _opciones_tipo(df_solicitudes)
        )

    if filtro_id_usuario is not None and not colaborador_activo:
        st.warning(
            "Este colaborador se encuentra **inactivo** en el sistema: no "
            "actualizó sus datos en el plazo de 6 meses o ya no forma parte de "
            "SETESA. Sus expedientes anteriores se conservan y aparecen abajo."
        )

    f_col4, f_col5 = st.columns(2)
    with f_col4:
        fecha_desde = st.date_input(
            "📅 Desde (periodo de ausencia)", value=None
        )
    with f_col5:
        fecha_hasta = st.date_input(
            "📅 Hasta (periodo de ausencia)", value=None
        )

    try:
        df_filtrado = filtrar_solicitudes(
            df_solicitudes,
            id_usuario=filtro_id_usuario,
            estado=filtro_estado,
            tipo=filtro_tipo,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    except ValueError as e:
        st.error(str(e))
        df_filtrado = df_solicitudes.iloc[0:0]

    st.caption(
        f"Mostrando **{len(df_filtrado)}** de **{len(df_solicitudes)}** "
        "expedientes."
    )

    if not df_filtrado.empty:
        with st.expander("📊 Distribución de los resultados filtrados"):
            col_estado, col_tipo = st.columns(2)
            with col_estado:
                st.write("**Por estado**")
                por_estado = (
                    df_filtrado["estado_workflow"]
                    .value_counts()
                    .rename_axis("estado_workflow")
                    .reset_index(name="cantidad")
                )
                st.dataframe(por_estado, hide_index=True, width="stretch")
            with col_tipo:
                st.write("**Por tipo de incidencia**")
                st.dataframe(
                    resumen_por_tipo(df_filtrado),
                    hide_index=True,
                    width="stretch",
                )

    _mostrar_tabla(df_filtrado)
    _mostrar_descargas(df_filtrado)
    _mostrar_evidencias(df_filtrado)

    if df_filtrado.empty:
        return

    # Contabilidad (HU-03): consulta y descarga, sin autorizar expedientes.
    if solo_lectura:
        _mostrar_trazabilidad(df_filtrado)
        return

    st.write("---")
    st.markdown("#### Gestión de Workflow (Autorización de Gerencia)")

    # Solo se permite la transición que corresponde a Gerencia.
    id_seleccionado = st.selectbox(
        "ID de la Solicitud", df_filtrado["id_solicitud"].tolist()
    )
    fila = df_filtrado[df_filtrado["id_solicitud"] == id_seleccionado].iloc[0]
    estado_actual = fila["estado_workflow"]

    st.write(f"**Estado actual:** {estado_actual}")

    if estado_actual == ESTADO_PENDIENTE_APROBACION_GERENCIA:
        from streamlit_drawable_canvas import st_canvas  # import perezoso

        st.info(
            "💡 Dibuje su firma en el recuadro; quedará estampada en el PDF "
            "oficial al finalizar el expediente."
        )
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=3,
            stroke_color="#000000",
            background_color="rgba(0, 0, 0, 0)",
            height=100,
            width=300,
            drawing_mode="freedraw",
            key=f"canvas_gerencia_{id_seleccionado}",
            return_image_data=True,
        )
        # Fase 16: Gerencia aprueba o deniega; ambas decisiones cierran el flujo.
        decision = st.radio(
            "Decisión de Gerencia",
            ["Aprobar", "Denegar"],
            horizontal=True,
            key=f"decision_gerencia_{id_seleccionado}",
        )
        denegar = decision == "Denegar"
        if denegar:
            observacion = st.text_area(
                "Motivo de la denegación (obligatorio; lo verá el consultor)",
                key=f"motivo_gerencia_{id_seleccionado}",
            )
        else:
            observacion = st.text_input("Observación de Gerencia (opcional)")
        btn_actualizar = st.button(
            "⛔ Denegar, Firmar y Finalizar Expediente"
            if denegar
            else "✅ Aprobar, Firmar y Finalizar Expediente",
            type="primary",
        )

        if btn_actualizar and id_seleccionado:
            firma_base64 = None
            if canvas_result.image_data is not None:
                firma_base64 = canvas_to_base64(canvas_result.image_data)

            if not firma_base64:
                st.error("❌ Debe dibujar su firma antes de finalizar el expediente.")
            else:
                try:
                    if denegar:
                        denegar_solicitud(
                            id_seleccionado,
                            st.session_state["id_usuario"],
                            observacion,
                            firma_base64,
                        )
                    else:
                        cambiar_estado(
                            id_seleccionado,
                            ESTADO_FINALIZADA,
                            st.session_state["id_usuario"],
                            observacion or "Aprobación final de Gerencia.",
                            firma_b64=firma_base64,
                        )
                except MotivoRequerido as e:
                    st.error(f"❌ {e}")
                except FirmaRequerida as e:
                    st.error(f"Debe firmar el expediente: {e}")
                except (TransicionInvalida, NoAutorizadoParaDenegar) as e:
                    st.error(f"No se puede finalizar: {e}")
                except Exception as e:
                    st.error(f"Error al actualizar el estado: {e}")
                else:
                    try:
                        ruta = generar_pdf_solicitud(id_seleccionado)
                        st.session_state["flash_gerencia"] = (
                            "success",
                            f"El expediente #{id_seleccionado} fue "
                            f"{'denegado' if denegar else 'aprobado'} y "
                            f"firmado. PDF final guardado en el repositorio "
                            f"({ruta}).",
                        )
                    except Exception as e:
                        st.session_state["flash_gerencia"] = (
                            "warning",
                            f"El expediente #{id_seleccionado} fue finalizado, "
                            f"pero no se pudo generar el PDF: {e}",
                        )
                    st.rerun()
    elif estado_actual == ESTADO_FINALIZADA:
        st.info("La solicitud está finalizada; no admite más cambios.")
    else:
        st.info(
            "Esta solicitud aún debe ser firmada por el Coordinador GTC. "
            "Gerencia solo puede autorizar expedientes que lleguen a "
            "'Pendiente de Aprobación Gerencia'."
        )

    with st.expander(f"🕓 Historial de estados del expediente #{id_seleccionado}"):
        df_movimientos = obtener_historial(id_seleccionado)
        if df_movimientos.empty:
            st.info("Sin movimientos registrados.")
        else:
            st.dataframe(df_movimientos, hide_index=True, width="stretch")
