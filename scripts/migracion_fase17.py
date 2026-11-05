# Migración Fase 17: repositorio persistente de expedientes (Supabase Storage).
# Uso: python scripts/migracion_fase17.py [--simular]
#
# Es idempotente:
#   1. Agrega solicitud.pdf_inmutable.
#   2. Crea el bucket privado (SUPABASE_BUCKET, por defecto "expedientes") si
#      SUPABASE_URL y SUPABASE_SERVICE_KEY están configurados.
#   3. Sube al repositorio los PDF que aún estén en el disco local
#      (ruta_pdf absoluta) y guarda su nueva clave; los de expedientes
#      finalizados quedan como PDF final inmutable.
#   4. Reaplica docs/triggers.sql.
#
# --simular hace rollback en la base y no sube archivos.

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.core.database import get_connection
from src.services import almacenamiento
from src.services.documentos import clave_pdf, sha256_bytes


def migrar(simular):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    print(f"[..] Repositorio: {almacenamiento.backend()}")
    if almacenamiento.backend() == "supabase" and not simular:
        estado = almacenamiento.crear_bucket()
        print(f"[ok] Bucket privado {estado}.")
    elif almacenamiento.backend() == "local":
        print(
            "[!] SUPABASE_URL / SUPABASE_SERVICE_KEY no configurados: se usa "
            "storage/repositorio/ (no apto para Render)."
        )

    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE solicitud ADD COLUMN IF NOT EXISTS pdf_inmutable "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            )
            print("[ok] Columna solicitud.pdf_inmutable disponible.")

            cur.execute(
                "SELECT id_solicitud, ruta_pdf, estado_workflow FROM solicitud "
                "WHERE ruta_pdf IS NOT NULL AND pdf_inmutable = FALSE"
            )
            locales = [f for f in cur.fetchall() if Path(f[1]).is_absolute()]
            # Ajuste de datos históricos sobre expedientes ya cerrados.
            cur.execute("SET LOCAL setesa.permitir_borrado = 'on'")
            subidos = 0
            for id_solicitud, ruta, estado in locales:
                archivo = Path(ruta)
                if not archivo.exists():
                    print(f"[!] #{id_solicitud}: no existe {archivo.name}; se regenerará al descargar.")
                    continue
                contenido = archivo.read_bytes()
                sello = sha256_bytes(contenido)
                final = estado == "Finalizada"
                clave = clave_pdf(id_solicitud, final, sello)
                if not simular:
                    try:
                        almacenamiento.guardar(clave, contenido, sobrescribir=not final)
                    except almacenamiento.ArchivoExistente:
                        pass
                cur.execute(
                    """
                    UPDATE solicitud
                    SET ruta_pdf = %s, pdf_hash = %s, pdf_hash_fecha = NOW(),
                        pdf_inmutable = %s
                    WHERE id_solicitud = %s
                    """,
                    (clave, sello, final, id_solicitud),
                )
                subidos += 1
            cur.execute("SET LOCAL setesa.permitir_borrado = 'off'")
            print(f"[ok] {subidos} PDF local(es) pasados al repositorio.")

            cur.execute((RAIZ / "docs" / "triggers.sql").read_text(encoding="utf-8"))
            print("[ok] Triggers reaplicados (PDF final inmutable).")

        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 17 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 17 (repositorio persistente)"
    )
    parser.add_argument("--simular", action="store_true",
                        help="Rollback en la base y sin subir archivos.")
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
