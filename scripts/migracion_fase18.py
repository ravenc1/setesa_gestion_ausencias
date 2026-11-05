# Migración Fase 18: evidencias adjuntas y avisos al finalizar.
# Uso: python scripts/migracion_fase18.py [--simular]
#
# Es idempotente:
#   1. Crea la tabla evidencia (metadatos; el archivo vive en el bucket).
#   2. Crea la tabla notificacion (avisos dentro del sistema).
#   3. Actualiza la descripción del rol Contabilidad ("Contabilidad y RR.HH.").
#   4. Reaplica docs/triggers.sql (evidencias, IGSS obligatoria y avisos).
#
# --simular aplica todo y al final hace rollback (no guarda cambios).

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.core.database import get_connection

DDL = [
    """
    CREATE TABLE IF NOT EXISTS evidencia (
        id_evidencia    SERIAL PRIMARY KEY,
        id_solicitud    INTEGER NOT NULL
                            REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
        id_usuario      INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
        nombre_original VARCHAR(255) NOT NULL,
        clave           VARCHAR(300) NOT NULL UNIQUE,
        tipo_mime       VARCHAR(50) NOT NULL,
        tamano          INTEGER NOT NULL,
        sha256          VARCHAR(64) NOT NULL,
        fecha           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT evidencia_tipo_check CHECK (
            tipo_mime IN ('application/pdf', 'image/jpeg', 'image/png')
        ),
        CONSTRAINT evidencia_tamano_check CHECK (
            tamano > 0 AND tamano <= 5242880
        )
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidencia_solicitud ON evidencia (id_solicitud)",
    """
    CREATE TABLE IF NOT EXISTS notificacion (
        id_notificacion SERIAL PRIMARY KEY,
        id_destinatario INTEGER NOT NULL
                            REFERENCES usuario(id_usuario) ON DELETE CASCADE,
        id_solicitud    INTEGER NOT NULL
                            REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
        tipo            VARCHAR(30) NOT NULL DEFAULT 'FINALIZADA',
        mensaje         TEXT NOT NULL,
        leida           BOOLEAN NOT NULL DEFAULT FALSE,
        fecha           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_notificacion_destinatario
        ON notificacion (id_destinatario, leida, fecha DESC)
    """,
    """
    UPDATE rol SET descripcion_rol =
        'Contabilidad y RR.HH.: consulta, descarga y control de expedientes; '
        'recibe el aviso al finalizar.'
    WHERE nombre_rol = 'Contabilidad'
    """,
]


def migrar(simular):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1
    try:
        with conn.cursor() as cur:
            for sentencia in DDL:
                cur.execute(sentencia)
            print("[ok] Tablas 'evidencia' y 'notificacion' disponibles.")
            cur.execute((RAIZ / "docs" / "triggers.sql").read_text(encoding="utf-8"))
            print("[ok] Triggers reaplicados (evidencias y avisos).")
        if simular:
            conn.rollback()
            print("\nSimulación terminada: no se guardó ningún cambio.")
        else:
            conn.commit()
            print("\nMigración Fase 18 completada.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 18 (evidencias y avisos)"
    )
    parser.add_argument("--simular", action="store_true",
                        help="Aplica la migración y hace rollback al final.")
    args = parser.parse_args()
    sys.exit(migrar(args.simular))
