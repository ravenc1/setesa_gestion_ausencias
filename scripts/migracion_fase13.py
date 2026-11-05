# Migración Fase 13: triggers de PostgreSQL (tesis, sección 3.6).
# Uso: python scripts/migracion_fase13.py [--simular] [--sin-cron]
#
# Es idempotente:
#   1. Crea o reemplaza las funciones y triggers de docs/triggers.sql.
#   2. Habilita pg_cron y programa la depuración diaria de vigencia
#      (09:00 UTC = 03:00 en Guatemala). Si pg_cron no está disponible, avisa
#      y sigue: la vigencia también se aplica por trigger y al entrar Gerencia.
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.core.database import get_connection

ARCHIVO_SQL = RAIZ / "docs" / "triggers.sql"
TAREA_CRON = "setesa-vigencia-diaria"
HORARIO_CRON = "0 9 * * *"

TRIGGERS_ESPERADOS = {
    ("usuario", "trg_usuario_vigencia"),
    ("solicitud", "trg_solicitud_insert"),
    ("solicitud", "trg_solicitud_update"),
    ("solicitud", "trg_solicitud_delete"),
    ("solicitud", "trg_solicitud_con_historial"),
    ("solicitud_historial", "trg_historial_insert"),
    ("solicitud_historial", "trg_historial_inmutable"),
}


def _programar_cron(cur):
    """Programa la depuración diaria. Devuelve True si quedó programada."""
    cur.execute("SAVEPOINT sp_cron")
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")
        cur.execute(
            "SELECT cron.schedule(%s, %s, %s)",
            (TAREA_CRON, HORARIO_CRON, "SELECT setesa_depurar_vigencia()"),
        )
        cur.execute("RELEASE SAVEPOINT sp_cron")
        return True
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT sp_cron")
        print(f"[!] No se pudo programar pg_cron: {e}".strip())
        print(
            "    Habilite la extensión pg_cron en Supabase (Database > "
            "Extensions) y vuelva a ejecutar este script."
        )
        return False


def migrar(simular, sin_cron):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute(ARCHIVO_SQL.read_text(encoding="utf-8"))
            cur.execute(
                """
                SELECT event_object_table, trigger_name
                  FROM information_schema.triggers
                 WHERE trigger_name LIKE 'trg\\_%%'
                """
            )
            creados = {tuple(fila) for fila in cur.fetchall()}
            faltantes = TRIGGERS_ESPERADOS - creados
            if faltantes:
                raise RuntimeError(f"Triggers no creados: {sorted(faltantes)}")
            for tabla, nombre in sorted(TRIGGERS_ESPERADOS):
                print(f"[ok] {tabla}.{nombre}")

            if sin_cron:
                print("[--] pg_cron omitido (--sin-cron).")
            elif _programar_cron(cur):
                print(
                    f"[ok] pg_cron: '{TAREA_CRON}' programada ({HORARIO_CRON} UTC)."
                )

        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 13 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 13 (triggers de PostgreSQL)"
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Aplica la migración y hace rollback al final.",
    )
    parser.add_argument(
        "--sin-cron",
        action="store_true",
        help="No programa la depuración diaria con pg_cron.",
    )
    args = parser.parse_args()
    sys.exit(migrar(args.simular, args.sin_cron))
