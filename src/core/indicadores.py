# Fase 21: indicadores del dashboard (tesis, tabla de variables: "Tiempo
# promedio de aprobación y porcentaje de usuarios inactivos").
#
# - Tiempo promedio de aprobación: desde que el consultor registra la solicitud
#   hasta que se resuelve (Aprobada o Denegada), y por etapa (banco y Gerencia).
# - Usuarios vigentes e inactivos (baja lógica), con el porcentaje de inactivos
#   y cuántos deben actualizar sus datos en los próximos 30 días.

import pandas as pd

from src.core.database import get_engine
from src.core.vigencia import DIAS_AVISO, ROLES_CON_ACTUALIZACION


def formatear_duracion(duracion):
    """'2 d 3 h', '5 h 20 min' o '—' si no hay datos."""
    if duracion is None or pd.isna(duracion):
        return "—"
    minutos = int(duracion.total_seconds() // 60)
    dias, resto = divmod(minutos, 1440)
    horas, mins = divmod(resto, 60)
    if dias:
        return f"{dias} d {horas} h"
    if horas:
        return f"{horas} h {mins} min"
    return f"{mins} min"


def obtener_tiempos_resolucion():
    """Solicitudes resueltas con las fechas de cada hito."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT s.id_solicitud, s.fecha_creacion, s.fecha_resolucion, s.resolucion,
               (SELECT MIN(h.fecha) FROM solicitud_historial h
                 WHERE h.id_solicitud = s.id_solicitud
                   AND h.estado_nuevo IN
                       ('Pendiente de Aprobación Gerencia', 'Finalizada'))
                   AS fecha_banco
        FROM solicitud s
        WHERE s.estado_workflow = 'Finalizada' AND s.fecha_resolucion IS NOT NULL
        """,
        engine,
        parse_dates=["fecha_creacion", "fecha_resolucion", "fecha_banco"],
    )


def calcular_tiempos(df):
    """Promedios de tiempo de resolución, en total y por etapa.

    - ``total``: de la creación a la resolución.
    - ``banco``: de la creación al visto bueno (o denegación) del banco.
    - ``gerencia``: del visto bueno del banco a la resolución de Gerencia;
      solo cuenta los expedientes que llegaron a Gerencia.
    """
    vacio = {
        "resueltas": 0,
        "total": None,
        "banco": None,
        "gerencia": None,
        "aprobadas": None,
        "denegadas": None,
    }
    if df is None or df.empty:
        return vacio

    df = df.dropna(subset=["fecha_creacion", "fecha_resolucion"]).copy()
    if df.empty:
        return vacio

    total = df["fecha_resolucion"] - df["fecha_creacion"]
    banco = df["fecha_banco"] - df["fecha_creacion"]
    llegaron = df["fecha_banco"] < df["fecha_resolucion"]
    gerencia = (df["fecha_resolucion"] - df["fecha_banco"])[llegaron]

    def promedio(serie):
        serie = serie.dropna()
        return serie.mean() if not serie.empty else None

    return {
        "resueltas": len(df),
        "total": promedio(total),
        "banco": promedio(banco),
        "gerencia": promedio(gerencia),
        "aprobadas": promedio(total[df["resolucion"] == "Aprobada"]),
        "denegadas": promedio(total[df["resolucion"] == "Denegada"]),
    }


def obtener_usuarios():
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT r.nombre_rol, COALESCE(u.estado_vigencia, TRUE) AS vigente,
               u.fecha_actualizacion_datos
        FROM usuario u JOIN rol r ON u.id_rol = r.id_rol
        """,
        engine,
        parse_dates=["fecha_actualizacion_datos"],
    )


def resumen_usuarios(df, hoy=None):
    """Vigentes, inactivos, % de inactivos y usuarios por vencer."""
    vacio = {"total": 0, "vigentes": 0, "inactivos": 0,
             "pct_inactivos": 0.0, "por_vencer": 0}
    if df is None or df.empty:
        return vacio
    hoy = pd.Timestamp(hoy) if hoy is not None else pd.Timestamp.today().normalize()

    vigentes = int(df["vigente"].sum())
    total = len(df)
    activos = df[df["vigente"]]
    exigen = activos[activos["nombre_rol"].isin(ROLES_CON_ACTUALIZACION)]
    limite = exigen["fecha_actualizacion_datos"] + pd.DateOffset(months=6)
    por_vencer = int(((limite - hoy).dt.days <= DIAS_AVISO).sum())
    return {
        "total": total,
        "vigentes": vigentes,
        "inactivos": total - vigentes,
        "pct_inactivos": round((total - vigentes) / total * 100, 1),
        "por_vencer": por_vencer,
    }
