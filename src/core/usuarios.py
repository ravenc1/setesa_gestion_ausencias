# Consultas de usuarios por rol (H-18: jefe GTC desde los usuarios reales).

import pandas as pd

from src.core.database import get_engine


def listar_usuarios_por_rol(nombre_rol, solo_vigentes=True):
    """Devuelve los usuarios de un rol, ordenados por nombre."""
    engine = get_engine()
    if engine is None:
        return pd.DataFrame(columns=["id_usuario", "nombre_completo"])

    query = """
        SELECT u.id_usuario, u.nombre_completo
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE r.nombre_rol = %s
    """
    params = [nombre_rol]
    if solo_vigentes:
        query += " AND u.estado_vigencia = TRUE"
    query += " ORDER BY u.nombre_completo"

    return pd.read_sql_query(query, engine, params=tuple(params))


def listar_coordinadores(solo_vigentes=True):
    """Atajo para el jefe inmediato GTC (rol Coordinador GTC)."""
    return listar_usuarios_por_rol("Coordinador GTC", solo_vigentes=solo_vigentes)
