# Migración Fase 15: registro de recordatorios por correo.
# Uso: python scripts/migracion_fase15.py [--simular]
#
# Es idempotente: crea la tabla aviso_actualizacion y su índice. Cada fila es
# un correo de recordatorio (etapa de 30, 15, 7 o 1 día antes del plazo).

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection

DDL = [
    """
    CREATE TABLE IF NOT EXISTS aviso_actualizacion (
        id_aviso     SERIAL PRIMARY KEY,
        id_usuario   INTEGER NOT NULL
                         REFERENCES usuario(id_usuario) ON DELETE CASCADE,
        fecha_limite DATE NOT NULL,
        umbral       INTEGER NOT NULL,
        estado       VARCHAR(10) NOT NULL,
        detalle      TEXT,
        fecha_envio  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT aviso_actualizacion_unico
            UNIQUE (id_usuario, fecha_limite, umbral),
        CONSTRAINT aviso_actualizacion_estado_check
            CHECK (estado IN ('ENVIADO', 'ERROR')),
        CONSTRAINT aviso_actualizacion_umbral_check
            CHECK (umbral IN (30, 15, 7, 1))
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_aviso_actualizacion_fecha
        ON aviso_actualizacion (fecha_envio DESC)
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
        print("[ok] Tabla 'aviso_actualizacion' disponible.")
        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 15 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 15 (recordatorios por correo)"
    )
    parser.add_argument("--simular", action="store_true",
                        help="Aplica la migración y hace rollback al final.")
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
