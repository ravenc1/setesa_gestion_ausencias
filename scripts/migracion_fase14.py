# Migración Fase 14: módulo "Mis datos" y vigencia por actualización de datos.
# Uso: python scripts/migracion_fase14.py [--simular]
#
# Es idempotente:
#   1. Agrega a usuario: puesto, codigo_empleado, telefono (cifrado) y
#      fecha_actualizacion_datos.
#   2. Precarga puesto y código desde la última solicitud de cada usuario.
#   3. Inicia el plazo de 6 meses de los usuarios existentes desde hoy, para
#      que nadie quede dado de baja por el cambio de regla.
#   4. Admite la acción ACTUALIZACION_DATOS en usuario_log.
#   5. Reaplica docs/triggers.sql (vigencia medida por la actualización).
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.core.database import get_connection

COLUMNAS = [
    "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS puesto VARCHAR(150)",
    "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS codigo_empleado VARCHAR(50)",
    "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS telefono TEXT",
    "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS fecha_actualizacion_datos TIMESTAMP",
]

PRECARGA = """
    UPDATE usuario u
       SET puesto = COALESCE(u.puesto, s.puesto),
           codigo_empleado = COALESCE(u.codigo_empleado, s.codigo_empleado)
      FROM (
            SELECT DISTINCT ON (id_usuario) id_usuario, puesto, codigo_empleado
              FROM solicitud
             ORDER BY id_usuario, fecha_creacion DESC
           ) s
     WHERE s.id_usuario = u.id_usuario
       AND (u.puesto IS NULL OR u.codigo_empleado IS NULL)
"""

ACCIONES_LOG = (
    "'CREACION', 'EDICION', 'BAJA', 'REACTIVACION', 'RESET_PASSWORD', "
    "'ACTUALIZACION_DATOS'"
)


def migrar(simular):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn.cursor() as cur:
            for sentencia in COLUMNAS:
                cur.execute(sentencia)
            print("[ok] Columnas de 'Mis datos' disponibles en usuario.")

            cur.execute(PRECARGA)
            print(f"[ok] {cur.rowcount} usuario(s) con puesto/código precargados.")

            cur.execute(
                "UPDATE usuario SET fecha_actualizacion_datos = NOW() "
                "WHERE fecha_actualizacion_datos IS NULL"
            )
            print(f"[ok] {cur.rowcount} usuario(s) inician su plazo de 6 meses hoy.")
            cur.execute(
                "ALTER TABLE usuario ALTER COLUMN fecha_actualizacion_datos "
                "SET DEFAULT NOW()"
            )
            cur.execute(
                "ALTER TABLE usuario ALTER COLUMN fecha_actualizacion_datos "
                "SET NOT NULL"
            )

            cur.execute(
                "ALTER TABLE usuario_log DROP CONSTRAINT IF EXISTS "
                "usuario_log_accion_check"
            )
            cur.execute(
                "ALTER TABLE usuario_log ADD CONSTRAINT usuario_log_accion_check "
                f"CHECK (accion IN ({ACCIONES_LOG}))"
            )
            print("[ok] usuario_log admite ACTUALIZACION_DATOS.")

            cur.execute((RAIZ / "docs" / "triggers.sql").read_text(encoding="utf-8"))
            print("[ok] Triggers reaplicados (vigencia por actualización de datos).")

        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 14 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 14 (Mis datos y vigencia por actualización)"
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Aplica la migración y hace rollback al final.",
    )
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
