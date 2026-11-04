# Migración Fase 7: rol Contabilidad (HU-03 / D-02).
# Uso: python scripts/migracion_fase7.py [--usuario-demo]
#
# Es idempotente:
#   1. Crea el rol "Contabilidad" (solo lectura del repositorio de expedientes).
#   2. Con --usuario-demo, crea una cuenta de prueba con rol Contabilidad.
#
# La cuenta de demostración usa una contraseña temporal: cámbiela o elimínela
# antes de la entrega definitiva.

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection
from src.core.security import hash_password

ROL = "Contabilidad"
DESCRIPCION = (
    "Solo lectura: consulta el repositorio de expedientes y descarga el PDF "
    "final (HU-03)."
)

DEMO_CORREO = "contabilidad.prueba@setesa.gt"
DEMO_NOMBRE = "CONTABILIDAD PRUEBA"
DEMO_PASSWORD = "Setsa-2026#Conta"


def migrar(crear_demo):
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Rol de solo lectura.
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

                # 2. Cuenta de demostración opcional.
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

        print("\nMigración Fase 7 completada.")
        return 0
    except Exception as e:
        print(f"\nMigración abortada (rollback): {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migración Fase 7 (rol Contabilidad)")
    parser.add_argument(
        "--usuario-demo",
        action="store_true",
        help="Crea la cuenta de prueba con rol Contabilidad.",
    )
    args = parser.parse_args()
    sys.exit(migrar(args.usuario_demo))
