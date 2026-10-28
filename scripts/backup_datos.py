# Backup lógico de las tablas del proyecto en formato JSON.
# Uso: python scripts/backup_datos.py
#
# Genera storage/backups/backup_YYYYMMDD_HHMMSS.json con el contenido de
# rol, usuario y solicitud (incluye hashes y firmas: NO versionar).

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import STORAGE_DIR
from src.core.database import get_connection

BACKUP_DIR = STORAGE_DIR / "backups"
TABLAS = ("rol", "usuario", "solicitud")


def serializar(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return valor.decode("utf-8", errors="replace")
    return valor


def respaldar():
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destino = BACKUP_DIR / f"backup_{datetime.now():%Y%m%d_%H%M%S}.json"

    datos = {}
    try:
        cursor = conn.cursor()
        for tabla in TABLAS:
            cursor.execute(f"SELECT * FROM {tabla} ORDER BY 1")
            columnas = [d[0] for d in cursor.description]
            filas = [
                {col: serializar(val) for col, val in zip(columnas, fila)}
                for fila in cursor.fetchall()
            ]
            datos[tabla] = {"columnas": columnas, "filas": filas}
        cursor.close()
    finally:
        conn.close()

    destino.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = sum(len(t["filas"]) for t in datos.values())
    print(f"Backup generado: {destino}")
    print(f"Registros respaldados: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(respaldar())
