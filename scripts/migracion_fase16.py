# Migración Fase 16: resolución Aprobada/Denegada de los expedientes.
# Uso: python scripts/migracion_fase16.py [--simular]
#
# Es idempotente:
#   1. Agrega a solicitud: resolucion, motivo_resolucion (cifrado),
#      fecha_resolucion e id_resuelve.
#   2. Marca como 'Aprobada' los expedientes ya finalizados (antes de esta
#      fase solo existía la aprobación).
#   3. Exige que todo expediente Finalizado tenga resolución, y solo él.
#   4. Reaplica docs/triggers.sql (denegación por Coordinador GTC o Gerencia).
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.core.database import get_connection

COLUMNAS = [
    "ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS resolucion VARCHAR(10)",
    "ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS motivo_resolucion TEXT",
    "ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS fecha_resolucion TIMESTAMP",
    """
    ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS id_resuelve INTEGER
        REFERENCES usuario(id_usuario) ON DELETE SET NULL
    """,
]

RESTRICCIONES = [
    "ALTER TABLE solicitud DROP CONSTRAINT IF EXISTS solicitud_resolucion_check",
    """
    ALTER TABLE solicitud ADD CONSTRAINT solicitud_resolucion_check
        CHECK (resolucion IN ('Aprobada', 'Denegada'))
    """,
    "ALTER TABLE solicitud DROP CONSTRAINT IF EXISTS solicitud_finalizada_resolucion_check",
    """
    ALTER TABLE solicitud ADD CONSTRAINT solicitud_finalizada_resolucion_check
        CHECK ((estado_workflow = 'Finalizada') = (resolucion IS NOT NULL))
    """,
]


def migrar(simular):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn.cursor() as cur:
            for sentencia in COLUMNAS:
                cur.execute(sentencia)
            print("[ok] Columnas de resolución disponibles en solicitud.")

            # Los expedientes finalizados son inalterables (Fase 13): este
            # ajuste de datos históricos se habilita solo en esta transacción.
            cur.execute("SET LOCAL setesa.permitir_borrado = 'on'")
            cur.execute(
                """
                UPDATE solicitud s
                   SET resolucion = 'Aprobada',
                       fecha_resolucion = COALESCE(
                           (SELECT MAX(h.fecha) FROM solicitud_historial h
                             WHERE h.id_solicitud = s.id_solicitud
                               AND h.estado_nuevo = 'Finalizada'),
                           s.fecha_creacion)
                 WHERE s.estado_workflow = 'Finalizada'
                   AND s.resolucion IS NULL
                """
            )
            print(f"[ok] {cur.rowcount} expediente(s) finalizado(s) marcados como Aprobada.")
            cur.execute("SET LOCAL setesa.permitir_borrado = 'off'")

            for sentencia in RESTRICCIONES:
                cur.execute(sentencia)
            print("[ok] Restricciones de resolución aplicadas.")

            cur.execute((RAIZ / "docs" / "triggers.sql").read_text(encoding="utf-8"))
            print("[ok] Triggers reaplicados (denegación).")

        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 16 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 16 (resolución Aprobada/Denegada)"
    )
    parser.add_argument("--simular", action="store_true",
                        help="Aplica la migración y hace rollback al final.")
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
