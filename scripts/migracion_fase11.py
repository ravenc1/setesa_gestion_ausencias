# Migración Fase 11: bandeja del Coordinador GTC limitada a su equipo.
# Uso: python scripts/migracion_fase11.py [--simular] [--asignar-sin-match ID]
#
# Es idempotente:
#   1. Agrega solicitud.id_coordinador (FK a usuario) y su índice.
#   2. Llena id_coordinador en las solicitudes existentes cuyo jefe_gtc
#      coincide con el nombre de un usuario con rol Coordinador GTC.
#   3. Lista las solicitudes que quedaron sin coordinador. Con
#      --asignar-sin-match ID se asignan a ese Coordinador GTC.
#
# --simular ejecuta todo y al final hace rollback: sirve para revisar el
# resultado sin modificar la base de datos.

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection

DDL = [
    """
    ALTER TABLE solicitud
        ADD COLUMN IF NOT EXISTS id_coordinador INTEGER
            REFERENCES usuario(id_usuario) ON DELETE SET NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_solicitud_coordinador_estado
        ON solicitud (id_coordinador, estado_workflow)
    """,
]

# Empareja por nombre (sin distinguir mayúsculas ni espacios extremos). Si dos
# coordinadores tuvieran el mismo nombre, no se adivina: queda sin asignar.
RELLENO = """
    UPDATE solicitud s
       SET id_coordinador = c.id_usuario
      FROM (
            SELECT UPPER(TRIM(u.nombre_completo)) AS nombre,
                   MIN(u.id_usuario) AS id_usuario
              FROM usuario u
              JOIN rol r ON u.id_rol = r.id_rol
             WHERE r.nombre_rol = 'Coordinador GTC'
             GROUP BY UPPER(TRIM(u.nombre_completo))
            HAVING COUNT(*) = 1
           ) c
     WHERE s.id_coordinador IS NULL
       AND UPPER(TRIM(s.jefe_gtc)) = c.nombre
"""


def _es_coordinador(cur, id_usuario):
    cur.execute(
        """
        SELECT u.nombre_completo
          FROM usuario u
          JOIN rol r ON u.id_rol = r.id_rol
         WHERE u.id_usuario = %s AND r.nombre_rol = 'Coordinador GTC'
        """,
        (id_usuario,),
    )
    fila = cur.fetchone()
    return fila[0] if fila else None


def migrar(simular, asignar_a):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn.cursor() as cur:
            for sentencia in DDL:
                cur.execute(sentencia)
            print("[ok] Columna solicitud.id_coordinador e índice disponibles.")

            cur.execute(RELLENO)
            print(f"[ok] {cur.rowcount} solicitud(es) asignadas por nombre.")

            cur.execute(
                """
                SELECT id_solicitud, jefe_gtc, estado_workflow
                  FROM solicitud
                 WHERE id_coordinador IS NULL
                 ORDER BY id_solicitud
                """
            )
            sin_match = cur.fetchall()
            if sin_match:
                print(f"[!] {len(sin_match)} solicitud(es) sin coordinador:")
                for id_sol, jefe, estado in sin_match:
                    print(f"    #{id_sol}  jefe_gtc={jefe!r}  estado={estado}")

                if asignar_a is not None:
                    nombre = _es_coordinador(cur, asignar_a)
                    if not nombre:
                        raise ValueError(
                            f"El usuario {asignar_a} no tiene rol Coordinador GTC."
                        )
                    cur.execute(
                        """
                        UPDATE solicitud
                           SET id_coordinador = %s
                         WHERE id_coordinador IS NULL
                        """,
                        (asignar_a,),
                    )
                    print(
                        f"[ok] {cur.rowcount} solicitud(es) asignadas a "
                        f"{nombre} (id {asignar_a})."
                    )
                else:
                    print(
                        "    Use --asignar-sin-match ID para asignarlas a un "
                        "Coordinador GTC; mientras tanto no aparecen en "
                        "ninguna bandeja."
                    )
            else:
                print("[ok] Todas las solicitudes tienen coordinador asignado.")

        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 11 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 11 (coordinador asignado por solicitud)"
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Ejecuta la migración y hace rollback al final.",
    )
    parser.add_argument(
        "--asignar-sin-match",
        type=int,
        metavar="ID",
        help="Asigna a este Coordinador GTC las solicitudes sin coincidencia.",
    )
    args = parser.parse_args()
    sys.exit(migrar(args.simular, args.asignar_sin_match))
