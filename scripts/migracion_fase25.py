# Migración Fase 25: retiro de solicitudes por el consultor.
# Uso: python scripts/migracion_fase25.py [--simular]
#
# Es idempotente:
#   1. Admite la resolución "Retirada" en solicitud.
#   2. Reaplica docs/triggers.sql (retiro, historial y avisos).
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.core.database import get_connection

DDL = [
    "ALTER TABLE solicitud DROP CONSTRAINT IF EXISTS solicitud_resolucion_check",
    """
    ALTER TABLE solicitud ADD CONSTRAINT solicitud_resolucion_check
        CHECK (resolucion IN ('Aprobada', 'Denegada', 'Retirada'))
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
            print("[ok] solicitud admite la resolución Retirada.")
            cur.execute((RAIZ / "docs" / "triggers.sql").read_text(encoding="utf-8"))
            print("[ok] Triggers reaplicados.")
        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 25 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migración Fase 25 (retiro de solicitudes)")
    parser.add_argument("--simular", action="store_true",
                        help="Aplica la migración y hace rollback al final.")
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
