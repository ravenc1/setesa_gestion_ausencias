# Tarea diaria: correos para actualizar "Mis datos" (Fase 15).
# Uso: python scripts/enviar_recordatorios.py [--simular]
#
# La ejecuta GitHub Actions (.github/workflows/recordatorios.yml) todos los
# días. --simular lista a quién se escribiría, sin enviar ni registrar nada.
# Sale con código 1 si algún correo falló, para que la tarea quede en rojo.

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.avisos import enviar_recordatorios


def main(simular):
    resumen = enviar_recordatorios(simular=simular)
    for linea in resumen["detalle"]:
        print(linea)
    print(
        f"\nCandidatos: {resumen['candidatos']} · enviados: "
        f"{resumen['enviados']} · errores: {resumen['errores']}"
    )
    return 1 if resumen["errores"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Recordatorios por correo para actualizar Mis datos"
    )
    parser.add_argument("--simular", action="store_true",
                        help="No envía ni registra; solo informa.")
    args = parser.parse_args()
    sys.exit(main(args.simular))
