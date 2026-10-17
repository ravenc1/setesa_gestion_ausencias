# Migración: convierte contraseñas en texto plano a hashes PBKDF2-SHA256.
# Uso: python scripts/hash_passwords.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.database import get_connection
from src.core.security import es_hash, hash_password


def migrar():
    conn = get_connection()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id_usuario, correo_institucional, password_hash FROM usuario")
        usuarios = cursor.fetchall()

        migrados = 0
        for id_usuario, correo, password_hash in usuarios:
            if not es_hash(password_hash):
                cursor.execute(
                    "UPDATE usuario SET password_hash = %s WHERE id_usuario = %s",
                    (hash_password(password_hash), id_usuario),
                )
                migrados += 1
                print(f"  [hash] {correo}")
            else:
                print(f"  [ok]   {correo}")

        conn.commit()
        cursor.close()
        print(f"\nContraseñas migradas: {migrados} de {len(usuarios)} usuarios.")
    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
