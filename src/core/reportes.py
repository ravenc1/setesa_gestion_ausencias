# Filtros, indicadores y exportación del dashboard (RF-04 / HU-03).
#
# La lógica vive aquí, sin Streamlit, para poder probarla de forma aislada.
# El rango de fechas se aplica al periodo de la ausencia: se conservan las
# solicitudes que se solapan con el intervalo solicitado.

import datetime

import pandas as pd

from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)

COLUMNAS_EXPORTACION = [
    "id_solicitud",
    "nombre_completo",
    "tipo_ausencia",
    "fecha_inicio",
    "fecha_fin",
    "dias_solicitados",
    "estado_workflow",
    "fecha_creacion",
]


def filtrar_solicitudes(
    df,
    nombre=None,
    estado=None,
    tipo=None,
    fecha_desde=None,
    fecha_hasta=None,
):
    """Filtra el repositorio por nombre, estado, tipo y periodo de ausencia."""
    if df is None:
        return pd.DataFrame()

    resultado = df.copy()
    if resultado.empty:
        return resultado

    if nombre and str(nombre).strip():
        resultado = resultado[
            resultado["nombre_completo"].astype(str).str.contains(
                str(nombre).strip(), case=False, na=False, regex=False
            )
        ]

    if estado and estado != "Todos":
        resultado = resultado[resultado["estado_workflow"] == estado]

    if tipo and tipo != "Todos":
        resultado = resultado[resultado["tipo_ausencia"] == tipo]

    if fecha_desde is not None or fecha_hasta is not None:
        desde = pd.Timestamp(fecha_desde) if fecha_desde is not None else None
        hasta = pd.Timestamp(fecha_hasta) if fecha_hasta is not None else None
        if desde is not None and hasta is not None and desde > hasta:
            raise ValueError(
                "La fecha 'desde' no puede ser posterior a la fecha 'hasta'."
            )

        inicio = pd.to_datetime(resultado["fecha_inicio"], errors="coerce")
        fin = pd.to_datetime(resultado["fecha_fin"], errors="coerce")
        mascara = pd.Series(True, index=resultado.index)
        if desde is not None:
            mascara &= fin >= desde
        if hasta is not None:
            mascara &= inicio <= hasta
        resultado = resultado[mascara]

    return resultado


def calcular_kpis(df):
    """Calcula los indicadores principales del dashboard."""
    vacio = {
        "total": 0,
        "ingresadas": 0,
        "pendientes_coordinador": 0,
        "pendientes_gerencia": 0,
        "finalizadas": 0,
    }
    if df is None or df.empty:
        return vacio

    estados = df["estado_workflow"].value_counts()
    return {
        "total": len(df),
        "ingresadas": int(estados.get(ESTADO_INGRESADA, 0)),
        "pendientes_coordinador": int(
            estados.get(ESTADO_PENDIENTE_FIRMA_COORDINADOR, 0)
        ),
        "pendientes_gerencia": int(
            estados.get(ESTADO_PENDIENTE_APROBACION_GERENCIA, 0)
        ),
        "finalizadas": int(estados.get(ESTADO_FINALIZADA, 0)),
    }


def resumen_por_tipo(df):
    """Devuelve el conteo de expedientes por tipo de incidencia."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["tipo_ausencia", "cantidad"])

    return (
        df["tipo_ausencia"]
        .fillna("Sin tipo")
        .value_counts()
        .rename_axis("tipo_ausencia")
        .reset_index(name="cantidad")
    )


def exportar_csv(df):
    """Serializa los expedientes filtrados a CSV compatible con Excel."""
    if df is None:
        df = pd.DataFrame()

    columnas = [columna for columna in COLUMNAS_EXPORTACION if columna in df.columns]
    return df[columnas].to_csv(index=False).encode("utf-8-sig")


def nombre_archivo_csv(fecha=None):
    """Nombre estable para la descarga del reporte CSV."""
    fecha = fecha or datetime.date.today()
    return f"setesa_solicitudes_{fecha.isoformat()}.csv"
