# Migración Fase 20: seguridad de sesión (límite de intentos de acceso).
# Uso: python scripts/migracion_fase20.py [--simular]
#
# Es idempotente:
#   1. Crea la tabla intento_login (conteo de fallos por correo).
#   2. Admite la acción DESBLOQUEO en usuario_log.
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection

ACCIONES_LOG = (
    "'CREACION', 'EDICION', 'BAJA', 'REACTIVACION', 'RESET_PASSWORD', "
    "'ACTUALIZACION_DATOS', 'DESBLOQUEO'"
)

DDL = [
    """
    CREATE TABLE IF NOT EXISTS intento_login (
        correo          VARCHAR(150) PRIMARY KEY,
        intentos        INTEGER NOT NULL DEFAULT 0,
        ultimo_intento  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        bloqueado_hasta TIMESTAMP
    )
    """,
    "ALTER TABLE usuario_log DROP CONSTRAINT IF EXISTS usuario_log_accion_check",
    f"""
    ALTER TABLE usuario_log ADD CONSTRAINT usuario_log_accion_check
        CHECK (accion IN ({ACCIONES_LOG}))
    """,
]


def migrar(simular):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1
    try:
        with conn.cursor() as cur:
            for sentencia in DDL:
                cur.execute(sentencia)
        print("[ok] Tabla 'intento_login' disponible.")
        print("[ok] usuario_log admite DESBLOQUEO.")
        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 20 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 20 (límite de intentos de acceso)"
    )
    parser.add_argument("--simular", action="store_true",
                        help="Aplica la migración y hace rollback al final.")
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
