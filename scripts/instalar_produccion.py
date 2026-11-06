# Instalador limpio de producción (Fase 26).
# Uso: python scripts/instalar_produccion.py [--env .env.produccion] [--solo-verificar]
#
# Deja una base de datos NUEVA y vacía lista para operar:
#   1. Aplica docs/schema.sql y, en orden, las migraciones estructurales.
#      NO se ejecutan las cuentas de demostración de las fases 7 y 9.
#   2. Crea el bucket privado de expedientes (migración de la fase 17).
#   3. Crea un único usuario con rol IT, con cambio de contraseña obligatorio
#      en el primer ingreso.
#
# Credenciales del primer usuario de IT (nunca en el repositorio):
#   IT_NOMBRE, IT_CORREO, IT_PASSWORD (variables de entorno); si faltan, se piden
#   por pantalla (la contraseña no se muestra).
#
# Salvaguardas: se niega a correr si la base ya tiene usuarios o si apunta a la
# misma base que el .env de pruebas.

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from dotenv import dotenv_values  # noqa: E402

# Orden obligatorio. Las fases 7 y 9 solo se usan SIN --usuario-demo.
MIGRACIONES = [
    ("migracion_fase1.py", []),
    ("migracion_fase3.py", []),
    ("migracion_fase5.py", []),
    ("migracion_fase6.py", []),
    ("migracion_fase7.py", []),
    ("migracion_fase8.py", []),
    ("migracion_fase9.py", []),
    ("migracion_fase11.py", []),
    ("migracion_fase13.py", []),
    ("migracion_fase14.py", []),
    ("migracion_fase15.py", []),
    ("migracion_fase16.py", []),
    ("migracion_fase17.py", []),
    ("migracion_fase18.py", []),
    ("migracion_fase20.py", []),
    ("migracion_fase21.py", []),
    ("migracion_fase24.py", []),
    ("migracion_fase25.py", []),
    ("migracion_fase26.py", []),
]

VARIABLES = ("DATABASE_URL", "FERNET_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")


def cargar_entorno(ruta):
    valores = dotenv_values(ruta)
    faltan = [v for v in VARIABLES if not valores.get(v)]
    if faltan:
        raise SystemExit(f"Faltan en {ruta}: {', '.join(faltan)}")
    return valores


def validar_destino(valores):
    """Impide instalar sobre la base de pruebas."""
    prueba = dotenv_values(RAIZ / ".env").get("DATABASE_URL")
    if prueba and prueba.strip() == valores["DATABASE_URL"].strip():
        raise SystemExit("La DATABASE_URL de producción es igual a la de pruebas.")


def conectar(url):
    import psycopg2

    return psycopg2.connect(url, connect_timeout=20)


def base_vacia(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.usuario')")
        if cur.fetchone()[0] is None:
            return True
        cur.execute("SELECT COUNT(*) FROM usuario")
        return cur.fetchone()[0] == 0


def ejecutar(script, args, entorno):
    ruta = RAIZ / "scripts" / script
    print(f"\n>>> {script} {' '.join(args)}".rstrip())
    r = subprocess.run(
        [sys.executable, str(ruta), *args], env=entorno, cwd=RAIZ
    )
    if r.returncode != 0:
        raise SystemExit(f"{script} falló (código {r.returncode}). Instalación detenida.")


def aplicar_esquema(conn):
    sql = (RAIZ / "docs" / "schema.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("[ok] docs/schema.sql aplicado.")


def pedir_credenciales():
    nombre = os.getenv("IT_NOMBRE") or input("Nombre completo del usuario de IT: ")
    correo = os.getenv("IT_CORREO") or input("Correo institucional: ")
    password = os.getenv("IT_PASSWORD") or getpass.getpass("Contraseña inicial: ")
    return nombre.strip(), correo, password


def crear_usuario_it(conn, nombre, correo, password):
    from src.core.gestion_usuarios import normalizar_correo, validar_password
    from src.core.security import hash_password

    correo = normalizar_correo(correo)
    validar_password(password)
    with conn.cursor() as cur:
        cur.execute("SELECT id_rol FROM rol WHERE nombre_rol = 'IT'")
        fila = cur.fetchone()
        if not fila:
            raise SystemExit("No existe el rol IT: el esquema no quedó completo.")
        cur.execute(
            """
            INSERT INTO usuario
                (id_rol, nombre_completo, correo_institucional, password_hash,
                 estado_vigencia, ultima_actividad, debe_cambiar_password)
            VALUES (%s, %s, %s, %s, TRUE, NOW(), TRUE)
            RETURNING id_usuario
            """,
            (fila[0], nombre, correo, hash_password(password)),
        )
        id_usuario = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO usuario_log (id_ejecutor, id_afectado, accion, detalle)
            VALUES (%s, %s, 'CREACION', 'Instalación inicial de producción')
            """,
            (id_usuario, id_usuario),
        )
    conn.commit()
    print(f"[ok] Usuario IT creado: {correo} (debe cambiar la contraseña al ingresar).")


def resumen(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
        tablas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM pg_trigger WHERE NOT tgisinternal")
        triggers = cur.fetchone()[0]
        cur.execute(
            "SELECT r.nombre_rol, COUNT(u.id_usuario) FROM rol r "
            "LEFT JOIN usuario u USING (id_rol) GROUP BY 1 ORDER BY 1"
        )
        roles = cur.fetchall()
    print(f"\nTablas: {tablas} | triggers: {triggers}")
    for rol, n in roles:
        print(f"  rol {rol}: {n} usuario(s)")


def main():
    parser = argparse.ArgumentParser(description="Instalador limpio de producción (Fase 26).")
    parser.add_argument("--env", default=str(RAIZ / ".env.produccion"))
    parser.add_argument("--solo-verificar", action="store_true",
                        help="Solo muestra el resumen de la base; no instala.")
    args = parser.parse_args()

    valores = cargar_entorno(args.env)
    validar_destino(valores)
    entorno = {**os.environ, **{v: valores[v] for v in VARIABLES}}
    for extra in ("SMTP_HOST", "SMTP_PORT", "SMTP_USUARIO", "SMTP_PASSWORD",
                  "SMTP_REMITENTE", "APP_URL", "SUPABASE_BUCKET", "SOPORTE_CORREO"):
        if valores.get(extra):
            entorno[extra] = valores[extra]

    conn = conectar(valores["DATABASE_URL"])
    try:
        if args.solo_verificar:
            resumen(conn)
            return 0
        if not base_vacia(conn):
            raise SystemExit("La base ya tiene usuarios: no se instala encima.")
        nombre, correo, password = pedir_credenciales()
        aplicar_esquema(conn)
        conn.close()
        for script, extra in MIGRACIONES:
            ejecutar(script, extra, entorno)
        conn = conectar(valores["DATABASE_URL"])
        crear_usuario_it(conn, nombre, correo, password)
        resumen(conn)
        print("\nInstalación de producción completada.")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
