# Ejecución semestral del algoritmo de vigencia (V-07).
# Uso:
#   python scripts/vigencia_semestral.py           # solo si el periodo venció
#   python scripts/vigencia_semestral.py --forzar  # ejecuta siempre
#
# Pensado para un Programador de tareas / cron. Deja auditoría en vigencia_log.

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.vigencia import (
    ACCION_AUTOMATICA,
    debe_ejecutarse_automaticamente,
    ejecutar_depuracion,
)


def main():
    parser = argparse.ArgumentParser(
        description="Depuración semestral de usuarios inactivos (baja lógica)."
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Ejecuta la depuración aunque no hayan pasado 6 meses.",
    )
    args = parser.parse_args()

    if not args.forzar and not debe_ejecutarse_automaticamente():
        print("Aún no corresponde: hay una depuración en los últimos 6 meses.")
        return 0

    df_afectados, id_log = ejecutar_depuracion(
        id_ejecutor=None, accion=ACCION_AUTOMATICA
    )
    print(f"Ejecución registrada con id_log={id_log}.")
    if df_afectados.empty:
        print("Sin usuarios afectados.")
    else:
        print(f"Usuarios dados de baja lógica: {len(df_afectados)}")
        for fila in df_afectados.itertuples(index=False):
            print(
                f"  - #{fila.id_usuario} {fila.nombre_completo} "
                f"({fila.correo_institucional}) última actividad: "
                f"{fila.ultima_actividad}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
