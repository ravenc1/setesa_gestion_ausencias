# Migración Fase 21: catálogo mantenible de motivos de ausencia.
# Uso: python scripts/migracion_fase21.py [--simular]
#
# Es idempotente:
#   1. Crea la tabla motivo_ausencia.
#   2. Siembra los 22 motivos de la plantilla oficial (VACACION y
#      SUSPENSIÓN IGSS quedan protegidos: tienen reglas propias).
#   3. Reaplica docs/triggers.sql (solo se registran motivos activos).
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.core.catalogos import OPCIONES_AUSENCIA
from src.core.database import get_connection
from src.core.motivos import PROTEGIDOS

DDL = [
    """
    CREATE TABLE IF NOT EXISTS motivo_ausencia (
        id_motivo      SERIAL PRIMARY KEY,
        nombre         VARCHAR(50) NOT NULL,
        activo         BOOLEAN NOT NULL DEFAULT TRUE,
        en_plantilla   BOOLEAN NOT NULL DEFAULT FALSE,
        protegido      BOOLEAN NOT NULL DEFAULT FALSE,
        id_creador     INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
        fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_motivo_ausencia_nombre
        ON motivo_ausencia (UPPER(nombre))
    """,
]


def sembrar(cur):
    """Inserta los motivos de la plantilla que falten. Devuelve cuántos."""
    nuevos = 0
    for nombre in OPCIONES_AUSENCIA:
        cur.execute(
            """
            INSERT INTO motivo_ausencia (nombre, en_plantilla, protegido)
            VALUES (%s, TRUE, %s)
            ON CONFLICT (UPPER(nombre)) DO NOTHING
            """,
            (nombre, nombre in PROTEGIDOS),
        )
        nuevos += cur.rowcount
    return nuevos


def migrar(simular):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1
    try:
        with conn.cursor() as cur:
            for sentencia in DDL:
                cur.execute(sentencia)
            print("[ok] Tabla 'motivo_ausencia' disponible.")
            print(f"[ok] {sembrar(cur)} motivo(s) de la plantilla sembrados.")

            cur.execute(
                "SELECT DISTINCT s.tipo_ausencia FROM solicitud s "
                "LEFT JOIN motivo_ausencia m ON m.nombre = s.tipo_ausencia "
                "WHERE m.id_motivo IS NULL"
            )
            huerfanos = [f[0] for f in cur.fetchall()]
            if huerfanos:
                print(f"[!] Solicitudes con motivos fuera del catálogo: {huerfanos}")

            cur.execute((RAIZ / "docs" / "triggers.sql").read_text(encoding="utf-8"))
            print("[ok] Triggers reaplicados (catálogo de motivos).")
        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 21 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 21 (catálogo de motivos)"
    )
    parser.add_argument("--simular", action="store_true",
                        help="Aplica la migración y hace rollback al final.")
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
