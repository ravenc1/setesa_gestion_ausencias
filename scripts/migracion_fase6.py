# Migración Fase 6: sello SHA-256 del PDF (H-13) y cifrado en reposo (H-11).
# Uso:
#   python scripts/migracion_fase6.py
#   python scripts/migracion_fase6.py --cifrar-existentes
#
# Es idempotente:
#   1. Agrega solicitud.pdf_hash y solicitud.pdf_hash_fecha.
#   2. Con --cifrar-existentes, cifra explicación y firmas en texto claro.
#   3. Sella los PDF existentes que todavía no tienen hash.
#
# Antes de usar --cifrar-existentes ejecute scripts/backup_datos.py y conserve
# la FERNET_KEY: sin ella los datos cifrados no se pueden recuperar.

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.crypto import CAMPOS_SENSIBLES, CifradoError, cifrar, es_cifrado
from src.core.database import get_connection

BLOQUE_LECTURA = 64 * 1024


def _sha256(ruta):
    digest = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(BLOQUE_LECTURA), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _cifrar_existentes(cursor):
    cursor.execute(
        f"""
        SELECT id_solicitud, {", ".join(CAMPOS_SENSIBLES)}
        FROM solicitud
        """
    )
    filas = cursor.fetchall()
    actualizados = 0

    for fila in filas:
        id_solicitud = fila[0]
        originales = fila[1:]
        nuevos = [cifrar(valor) for valor in originales]
        cambio = any(
            not es_cifrado(original) and es_cifrado(nuevo)
            for original, nuevo in zip(originales, nuevos)
        )
        if not cambio:
            continue

        asignaciones = ", ".join(f"{campo} = %s" for campo in CAMPOS_SENSIBLES)
        cursor.execute(
            f"UPDATE solicitud SET {asignaciones} WHERE id_solicitud = %s",
            (*nuevos, id_solicitud),
        )
        actualizados += 1

    return actualizados


def _sellar_existentes(cursor):
    cursor.execute(
        """
        SELECT id_solicitud, ruta_pdf
        FROM solicitud
        WHERE ruta_pdf IS NOT NULL AND pdf_hash IS NULL
        """
    )
    sellados = 0
    for id_solicitud, ruta in cursor.fetchall():
        archivo = Path(ruta)
        if not archivo.exists():
            continue
        cursor.execute(
            """
            UPDATE solicitud
            SET pdf_hash = %s, pdf_hash_fecha = NOW()
            WHERE id_solicitud = %s
            """,
            (_sha256(archivo), id_solicitud),
        )
        sellados += 1
    return sellados


def migrar(cifrar_existentes=False):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Sello SHA-256 del PDF.
                cur.execute(
                    "ALTER TABLE solicitud "
                    "ADD COLUMN IF NOT EXISTS pdf_hash VARCHAR(64)"
                )
                cur.execute(
                    "ALTER TABLE solicitud "
                    "ADD COLUMN IF NOT EXISTS pdf_hash_fecha TIMESTAMP"
                )
                print("[ok] Columnas solicitud.pdf_hash y pdf_hash_fecha disponibles.")

                # 2. Cifrado de registros heredados (opcional).
                if cifrar_existentes:
                    actualizados = _cifrar_existentes(cur)
                    print(
                        "[ok] Solicitudes cifradas en esta ejecución: "
                        f"{actualizados}."
                    )
                else:
                    print(
                        "[ok] Cifrado de registros heredados omitido "
                        "(use --cifrar-existentes)."
                    )

                # 3. Sello de los PDF que ya existían.
                sellados = _sellar_existentes(cur)
                print(f"[ok] PDF existentes sellados en esta ejecución: {sellados}.")

        print("\nMigración Fase 6 completada.")
        return 0
    except CifradoError as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    except Exception as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(migrar(cifrar_existentes="--cifrar-existentes" in sys.argv))
