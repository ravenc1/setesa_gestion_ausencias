# Migración Fase 3: auditoría del algoritmo de vigencia.
# Uso: python scripts/migracion_fase3.py
#
# Es idempotente: puede ejecutarse varias veces sin duplicar objetos.
#   1. Crea la tabla vigencia_log si no existe.
#   2. Crea el índice por fecha de ejecución.
#   3. Verifica que ultima_actividad sea NOT NULL.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection

NOMBRE_CHECK = "vigencia_log_accion_check"


def migrar():
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Tabla de auditoría
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vigencia_log (
                        id_log SERIAL PRIMARY KEY,
                        fecha_ejecucion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        id_ejecutor INTEGER
                            REFERENCES usuario(id_usuario) ON DELETE SET NULL,
                        accion VARCHAR(20) NOT NULL,
                        usuarios_afectados INTEGER NOT NULL DEFAULT 0,
                        detalle TEXT
                    )
                    """
                )
                print("[ok] Tabla vigencia_log disponible.")

                # 2. CHECK de acciones válidas
                cur.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    (NOMBRE_CHECK,),
                )
                if not cur.fetchone():
                    cur.execute(
                        f"""
                        ALTER TABLE vigencia_log
                        ADD CONSTRAINT {NOMBRE_CHECK} CHECK (
                            accion IN ('DEPURACION', 'AUTOMATICA', 'REACTIVACION')
                        )
                        """
                    )
                    print("[ok] Restricción CHECK de acciones agregada.")
                else:
                    print("[ok] Restricción CHECK de acciones ya existente.")

                # 3. Índice de consulta
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_vigencia_log_fecha
                    ON vigencia_log (fecha_ejecucion DESC)
                    """
                )
                print("[ok] Índice de fecha disponible.")

                # 4. ultima_actividad debe ser obligatoria
                cur.execute(
                    """
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'usuario' AND column_name = 'ultima_actividad'
                    """
                )
                fila = cur.fetchone()
                if fila and fila[0] == "YES":
                    cur.execute(
                        "UPDATE usuario SET ultima_actividad = NOW() "
                        "WHERE ultima_actividad IS NULL"
                    )
                    cur.execute(
                        "ALTER TABLE usuario "
                        "ALTER COLUMN ultima_actividad SET NOT NULL"
                    )
                    print("[ok] ultima_actividad normalizada a NOT NULL.")
                else:
                    print("[ok] ultima_actividad ya es NOT NULL.")

        print("\nMigración Fase 3 completada.")
        return 0
    except Exception as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(migrar())
