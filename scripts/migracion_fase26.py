# Migración Fase 26: zona horaria de Guatemala en la base de datos.
# Uso: python scripts/migracion_fase26.py [--simular] [--env .env.produccion]
# Con --env toma DATABASE_URL de ese archivo (p. ej. para producción).
#
# Supabase trabaja en UTC: después de las 18:00 en Guatemala, NOW() y
# CURRENT_DATE ya marcan el día siguiente (fechas del PDF, vigencias, avisos).
# Fija la zona horaria de la base para que toda sesión nueva use la hora de
# Guatemala. Es idempotente. Conserva los datos: solo cambia cómo se interpretan
# NOW() y CURRENT_DATE desde ahora.
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from dotenv import dotenv_values

ZONA = "America/Guatemala"


def migrar(simular):
    from src.core.database import get_connection

    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            base = cur.fetchone()[0]
            cur.execute(f'ALTER DATABASE "{base}" SET timezone TO \'{ZONA}\'')
            print(f"[ok] Zona horaria de la base «{base}» = {ZONA}.")
        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 26 completada. Rige en las conexiones nuevas.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migración Fase 26 (zona horaria)")
    parser.add_argument("--simular", action="store_true",
                        help="Aplica la migración y hace rollback al final.")
    parser.add_argument("--env", help="Archivo con DATABASE_URL (p. ej. .env.produccion).")
    args = parser.parse_args()
    if args.env:
        url = dotenv_values(args.env).get("DATABASE_URL")
        if not url:
            raise SystemExit(f"Falta DATABASE_URL en {args.env}")
        os.environ["DATABASE_URL"] = url.strip()
    sys.exit(migrar(args.simular))
