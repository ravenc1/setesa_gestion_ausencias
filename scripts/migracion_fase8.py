# Migración Fase 8: recordatorios del consultor al banco (R-11).
# Uso: python scripts/migracion_fase8.py
#
# Es idempotente: puede ejecutarse varias veces sin duplicar objetos.
#   1. Crea la tabla recordatorio (aviso auditable, sin correo automático).
#   2. Crea los índices de consulta para la bandeja del Coordinador GTC.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection

DDL = [
    """
    CREATE TABLE IF NOT EXISTS recordatorio (
        id_recordatorio SERIAL PRIMARY KEY,
        id_solicitud    INTEGER NOT NULL
                            REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
        id_emisor       INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
        id_destinatario INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
        correo_destino  VARCHAR(150),
        mensaje         TEXT,
        fecha           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        atendido        BOOLEAN NOT NULL DEFAULT FALSE,
        fecha_atencion  TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recordatorio_destino
        ON recordatorio (id_destinatario, atendido, fecha DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recordatorio_solicitud
        ON recordatorio (id_solicitud, fecha DESC)
    """,
]


def migrar():
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn:
            with conn.cursor() as cursor:
                for sentencia in DDL:
                    cursor.execute(sentencia)
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'recordatorio'
                    ORDER BY ordinal_position
                    """
                )
                columnas = [fila[0] for fila in cursor.fetchall()]

        print("[ok] Tabla 'recordatorio' disponible.")
        print(f"[ok] Columnas: {', '.join(columnas)}.")
        print("\nMigración Fase 8 completada.")
        return 0
    except Exception as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(migrar())
