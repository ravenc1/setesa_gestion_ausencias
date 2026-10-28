# Migración Fase 1: historial de estados, normalización y restricciones.
# Uso: python scripts/migracion_fase1.py
#
# Es idempotente: puede ejecutarse varias veces sin duplicar datos.
#   1. Crea solicitud_historial si no existe.
#   2. Migra el estado legado "En revisión por jefe inmediato GTC".
#   3. Registra el estado inicial de las solicitudes que aún no tienen historial.
#   4. Agrega NOT NULL, CHECK e índices sobre estado_workflow.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psycopg2 import sql

from src.core.database import get_connection
from src.core.workflow import (
    ESTADOS_WORKFLOW,
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)

ESTADO_LEGADO = "En revisión por jefe inmediato GTC"
NOMBRE_CHECK = "solicitud_estado_workflow_check"
NOMBRE_CHECK_HISTORIAL = "solicitud_historial_estado_nuevo_check"


def migrar():
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Tabla de historial
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS solicitud_historial (
                        id_historial SERIAL PRIMARY KEY,
                        id_solicitud INTEGER NOT NULL
                            REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
                        estado_anterior VARCHAR(50),
                        estado_nuevo VARCHAR(50) NOT NULL,
                        id_usuario INTEGER
                            REFERENCES usuario(id_usuario) ON DELETE SET NULL,
                        fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        observacion TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_historial_solicitud
                    ON solicitud_historial (id_solicitud, fecha)
                    """
                )
                print("[ok] Tabla solicitud_historial disponible.")

                # 2. Estado legado -> estado del catálogo
                cur.execute(
                    "SELECT id_solicitud FROM solicitud WHERE estado_workflow = %s",
                    (ESTADO_LEGADO,),
                )
                legados = [fila[0] for fila in cur.fetchall()]
                for id_solicitud in legados:
                    cur.execute(
                        "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
                        (ESTADO_PENDIENTE_FIRMA_COORDINADOR, id_solicitud),
                    )
                    cur.execute(
                        """
                        INSERT INTO solicitud_historial
                            (id_solicitud, estado_anterior, estado_nuevo, observacion)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            id_solicitud,
                            ESTADO_LEGADO,
                            ESTADO_PENDIENTE_FIRMA_COORDINADOR,
                            "Migración Fase 1: estado legado normalizado al catálogo.",
                        ),
                    )
                print(f"[ok] Estados legados migrados: {len(legados)}.")

                # 2b. Solicitudes 'Ingresada' heredadas del flujo anterior.
                # En el flujo nuevo 'Ingresada' es transitorio: el registro se
                # confirma ya en 'Pendiente de Firma Coordinador'. Cualquier
                # fila confirmada en 'Ingresada' es un remanente y se avanza.
                cur.execute(
                    "SELECT id_solicitud FROM solicitud WHERE estado_workflow = %s",
                    (ESTADO_INGRESADA,),
                )
                ingresadas = [fila[0] for fila in cur.fetchall()]
                for id_solicitud in ingresadas:
                    cur.execute(
                        "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
                        (ESTADO_PENDIENTE_FIRMA_COORDINADOR, id_solicitud),
                    )
                    cur.execute(
                        """
                        INSERT INTO solicitud_historial
                            (id_solicitud, estado_anterior, estado_nuevo, observacion)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            id_solicitud,
                            ESTADO_INGRESADA,
                            ESTADO_PENDIENTE_FIRMA_COORDINADOR,
                            "Migración Fase 1: solicitud heredada avanzada a firma del Coordinador.",
                        ),
                    )
                print(f"[ok] Solicitudes 'Ingresada' heredadas avanzadas: {len(ingresadas)}.")

                # 3. Historial inicial para solicitudes sin registros
                cur.execute(
                    """
                    SELECT s.id_solicitud, s.estado_workflow, s.id_usuario
                    FROM solicitud s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM solicitud_historial h
                        WHERE h.id_solicitud = s.id_solicitud
                    )
                    """
                )
                sin_historial = cur.fetchall()
                for id_solicitud, estado, id_usuario in sin_historial:
                    cur.execute(
                        """
                        INSERT INTO solicitud_historial
                            (id_solicitud, estado_anterior, estado_nuevo, id_usuario, observacion)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            id_solicitud,
                            None,
                            estado,
                            id_usuario,
                            "Migración Fase 1: estado existente registrado en el historial.",
                        ),
                    )
                print(f"[ok] Historial inicial creado: {len(sin_historial)}.")

                # 4. Normalizar nulos y validar catálogo antes del CHECK
                cur.execute(
                    "UPDATE solicitud SET estado_workflow = %s WHERE estado_workflow IS NULL",
                    (ESTADO_INGRESADA,),
                )
                if cur.rowcount:
                    print(f"[ok] Estados nulos normalizados: {cur.rowcount}.")

                cur.execute(
                    sql.SQL(
                        "SELECT id_solicitud, estado_workflow FROM solicitud "
                        "WHERE estado_workflow NOT IN ({})"
                    ).format(
                        sql.SQL(", ").join(sql.Literal(e) for e in ESTADOS_WORKFLOW)
                    )
                )
                invalidos = cur.fetchall()
                if invalidos:
                    raise ValueError(
                        "Hay estados fuera del catálogo; corrija antes de continuar: "
                        f"{invalidos}"
                    )

                # 5. NOT NULL + CHECK
                cur.execute(
                    "ALTER TABLE solicitud ALTER COLUMN estado_workflow SET NOT NULL"
                )
                cur.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    (NOMBRE_CHECK,),
                )
                if not cur.fetchone():
                    cur.execute(
                        sql.SQL(
                            "ALTER TABLE solicitud ADD CONSTRAINT {} CHECK "
                            "(estado_workflow IN ({}))"
                        ).format(
                            sql.Identifier(NOMBRE_CHECK),
                            sql.SQL(", ").join(
                                sql.Literal(e) for e in ESTADOS_WORKFLOW
                            ),
                        )
                    )
                    print("[ok] Restricción CHECK agregada.")
                else:
                    print("[ok] Restricción CHECK ya existente.")

                # 5b. El historial solo puede registrar estados del catálogo.
                cur.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    (NOMBRE_CHECK_HISTORIAL,),
                )
                if not cur.fetchone():
                    cur.execute(
                        sql.SQL(
                            "ALTER TABLE solicitud_historial ADD CONSTRAINT {} CHECK "
                            "(estado_nuevo IN ({}))"
                        ).format(
                            sql.Identifier(NOMBRE_CHECK_HISTORIAL),
                            sql.SQL(", ").join(
                                sql.Literal(e) for e in ESTADOS_WORKFLOW
                            ),
                        )
                    )
                    print("[ok] Restricción CHECK del historial agregada.")
                else:
                    print("[ok] Restricción CHECK del historial ya existente.")

                # 6. Índice para bandejas y dashboard
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_solicitud_estado_fecha
                    ON solicitud (estado_workflow, fecha_creacion DESC)
                    """
                )
                print("[ok] Índice de estado/fecha disponible.")

        print("\nMigración Fase 1 completada.")
        return 0
    except Exception as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(migrar())
