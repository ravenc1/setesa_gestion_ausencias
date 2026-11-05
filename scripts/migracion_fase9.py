# Migración Fase 9: gestión de usuarios desde el panel (rol IT).
# Uso: python scripts/migracion_fase9.py [--usuario-demo]
#
# Es idempotente:
#   1. Crea el rol "IT" (solo gestión de usuarios).
#   2. Crea la tabla usuario_log con sus índices y su CHECK de acciones.
#   3. Con --usuario-demo, crea una cuenta de prueba con rol IT.
#
# La cuenta de demostración usa una contraseña temporal: cámbiela o elimínela
# antes de la entrega definitiva.

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection
from src.core.security import hash_password

ROL = "IT"
DESCRIPCION = (
    "Gestión de usuarios: altas, ediciones, bajas, reactivaciones y reseteo "
    "de contraseñas."
)

DEMO_CORREO = "it.prueba@setesa.gt"
DEMO_NOMBRE = "IT PRUEBA"
DEMO_PASSWORD = "Setsa-2026#IT"

DDL = [
    """
    CREATE TABLE IF NOT EXISTS usuario_log (
        id_log      SERIAL PRIMARY KEY,
        fecha       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        id_ejecutor INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
        id_afectado INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
        accion      VARCHAR(20) NOT NULL,
        detalle     TEXT,
        CONSTRAINT usuario_log_accion_check CHECK (
            accion IN ('CREACION', 'EDICION', 'BAJA', 'REACTIVACION',
                       'RESET_PASSWORD')
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_usuario_log_fecha
        ON usuario_log (fecha DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_usuario_log_afectado
        ON usuario_log (id_afectado, fecha DESC)
    """,
]


def migrar(crear_demo):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Rol de gestión de usuarios.
                cur.execute(
                    """
                    INSERT INTO rol (nombre_rol, descripcion_rol)
                    VALUES (%s, %s)
                    ON CONFLICT (nombre_rol) DO UPDATE
                        SET descripcion_rol = EXCLUDED.descripcion_rol
                    RETURNING id_rol
                    """,
                    (ROL, DESCRIPCION),
                )
                id_rol = cur.fetchone()[0]
                print(f"[ok] Rol '{ROL}' disponible (id_rol={id_rol}).")

                # 2. Auditoría y sus índices.
                for sentencia in DDL:
                    cur.execute(sentencia)
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'usuario_log'
                    ORDER BY ordinal_position
                    """
                )
                columnas = [fila[0] for fila in cur.fetchall()]
                print("[ok] Tabla 'usuario_log' disponible.")
                print(f"[ok] Columnas: {', '.join(columnas)}.")

                # 3. Cuenta de demostración opcional.
                if crear_demo:
                    cur.execute(
                        "SELECT id_usuario FROM usuario WHERE correo_institucional = %s",
                        (DEMO_CORREO,),
                    )
                    existente = cur.fetchone()
                    if existente:
                        cur.execute(
                            """
                            UPDATE usuario
                               SET id_rol = %s,
                                   estado_vigencia = TRUE,
                                   ultima_actividad = NOW()
                             WHERE correo_institucional = %s
                            """,
                            (id_rol, DEMO_CORREO),
                        )
                        print(
                            f"[ok] Usuario demo ya existente (id_usuario={existente[0]})."
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO usuario
                                (id_rol, nombre_completo, correo_institucional,
                                 password_hash, estado_vigencia, ultima_actividad)
                            VALUES (%s, %s, %s, %s, TRUE, NOW())
                            RETURNING id_usuario
                            """,
                            (
                                id_rol,
                                DEMO_NOMBRE,
                                DEMO_CORREO,
                                hash_password(DEMO_PASSWORD),
                            ),
                        )
                        print(
                            f"[ok] Usuario demo creado (id_usuario="
                            f"{cur.fetchone()[0]})."
                        )

        print("\nMigración Fase 9 completada.")
        return 0
    except Exception as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración Fase 9 (rol IT y auditoría de usuarios)"
    )
    parser.add_argument(
        "--usuario-demo",
        action="store_true",
        help="Crea la cuenta de prueba con rol IT.",
    )
    args = parser.parse_args()
    sys.exit(migrar(args.usuario_demo))
