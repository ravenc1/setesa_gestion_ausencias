# Migración Fase 5: saldo de vacaciones (RF-01) y catálogo de feriados (D-04).
# Uso: python scripts/migracion_fase5.py
#
# Es idempotente: puede ejecutarse varias veces sin duplicar objetos ni datos.
#   1. Agrega usuario.dias_vacaciones_asignados (15 por defecto).
#   2. Crea la tabla feriado con fecha única.
#   3. Siembra los feriados nacionales de 2025, 2026 y 2027.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection

NOMBRE_CHECK = "usuario_dias_vacaciones_check"
DIAS_DEFAULT = 15

# Feriados nacionales de Guatemala (días completos).
# Semana Santa: jueves, viernes y sábado santo.
FERIADOS = [
    ("2025-01-01", "Año Nuevo"),
    ("2025-04-17", "Jueves Santo"),
    ("2025-04-18", "Viernes Santo"),
    ("2025-04-19", "Sábado Santo"),
    ("2025-05-01", "Día del Trabajo"),
    ("2025-06-30", "Día del Ejército"),
    ("2025-09-15", "Independencia"),
    ("2025-10-20", "Revolución"),
    ("2025-11-01", "Todos los Santos"),
    ("2025-12-25", "Navidad"),
    ("2026-01-01", "Año Nuevo"),
    ("2026-04-02", "Jueves Santo"),
    ("2026-04-03", "Viernes Santo"),
    ("2026-04-04", "Sábado Santo"),
    ("2026-05-01", "Día del Trabajo"),
    ("2026-06-30", "Día del Ejército"),
    ("2026-09-15", "Independencia"),
    ("2026-10-20", "Revolución"),
    ("2026-11-01", "Todos los Santos"),
    ("2026-12-25", "Navidad"),
    ("2027-01-01", "Año Nuevo"),
    ("2027-03-25", "Jueves Santo"),
    ("2027-03-26", "Viernes Santo"),
    ("2027-03-27", "Sábado Santo"),
    ("2027-05-01", "Día del Trabajo"),
    ("2027-06-30", "Día del Ejército"),
    ("2027-09-15", "Independencia"),
    ("2027-10-20", "Revolución"),
    ("2027-11-01", "Todos los Santos"),
    ("2027-12-25", "Navidad"),
]


def migrar():
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Días asignados de vacaciones por usuario.
                cur.execute(
                    f"""
                    ALTER TABLE usuario
                    ADD COLUMN IF NOT EXISTS dias_vacaciones_asignados
                        INTEGER NOT NULL DEFAULT {DIAS_DEFAULT}
                    """
                )
                print("[ok] Columna usuario.dias_vacaciones_asignados disponible.")

                cur.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    (NOMBRE_CHECK,),
                )
                if not cur.fetchone():
                    cur.execute(
                        f"""
                        ALTER TABLE usuario
                        ADD CONSTRAINT {NOMBRE_CHECK}
                        CHECK (dias_vacaciones_asignados >= 0)
                        """
                    )
                    print("[ok] Restricción CHECK de días asignados agregada.")
                else:
                    print("[ok] Restricción CHECK de días asignados ya existente.")

                # 2. Catálogo de feriados.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feriado (
                        id_feriado SERIAL PRIMARY KEY,
                        fecha DATE NOT NULL UNIQUE,
                        nombre VARCHAR(120) NOT NULL
                    )
                    """
                )
                print("[ok] Tabla feriado disponible.")

                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_feriado_fecha
                    ON feriado (fecha)
                    """
                )
                print("[ok] Índice de feriados disponible.")

                # 3. Semilla idempotente de feriados.
                cur.executemany(
                    """
                    INSERT INTO feriado (fecha, nombre)
                    VALUES (%s, %s)
                    ON CONFLICT (fecha) DO NOTHING
                    """,
                    FERIADOS,
                )
                print(f"[ok] Feriados sembrados/verificados: {len(FERIADOS)}.")

        print("\nMigración Fase 5 completada.")
        return 0
    except Exception as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(migrar())
