# Respaldo y restauración completos (Fase 26).
#
#   python scripts/respaldo.py respaldar  [--env .env.produccion]
#   python scripts/respaldo.py restaurar CARPETA [--env .env.produccion]
#                              --confirmar-reemplazo [--simular]
#
# Respaldar: guarda TODAS las tablas del esquema public (un .jsonl por tabla) y
# los archivos del repositorio (PDF y evidencias del bucket) en
# storage/backups/respaldo_<fecha>/, con un manifiesto de conteos y sellos
# SHA-256. La carpeta contiene hashes de contraseña y datos cifrados: no se
# versiona (storage/backups/ está ignorado) y debe guardarse junto con la
# FERNET_KEY, sin la cual el contenido cifrado no se puede leer.
#
# Restaurar: VACÍA las tablas de la base destino y carga el respaldo en una sola
# transacción (todo o nada), verifica los conteos y reajusta las secuencias.
# --simular hace rollback al final: sirve para ensayar sin cambiar nada.

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from dotenv import dotenv_values  # noqa: E402

DIRECTORIO = RAIZ / "storage" / "backups"


def cargar_entorno(ruta):
    for clave, valor in dotenv_values(ruta).items():
        if valor:
            os.environ[clave] = valor


def conectar():
    import psycopg2

    return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)


def tablas_en_orden(cur):
    """Tablas de public ordenadas para que las referenciadas vayan primero."""
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
    )
    tablas = [f[0] for f in cur.fetchall()]
    cur.execute(
        """
        SELECT conrelid::regclass::text, confrelid::regclass::text
          FROM pg_constraint
         WHERE contype = 'f' AND connamespace = 'public'::regnamespace
        """
    )
    deps = {t: set() for t in tablas}
    for hijo, padre in cur.fetchall():
        if hijo != padre and hijo in deps and padre in deps:
            deps[hijo].add(padre)
    orden = []
    while deps:
        listas = sorted(t for t, d in deps.items() if not d)
        if not listas:
            raise SystemExit(f"Ciclo de claves foráneas entre: {sorted(deps)}")
        for t in listas:
            orden.append(t)
            del deps[t]
        for d in deps.values():
            d.difference_update(listas)
    return orden


def sha256(contenido):
    return hashlib.sha256(contenido).hexdigest()


def claves_de_archivos(cur):
    cur.execute(
        "SELECT ruta_pdf FROM solicitud "
        "WHERE ruta_pdf IS NOT NULL AND ruta_pdf LIKE 'pdf/%'"
    )
    claves = {f[0] for f in cur.fetchall()}
    cur.execute("SELECT clave FROM evidencia")
    claves |= {f[0] for f in cur.fetchall()}
    return sorted(claves)


def respaldar(args):
    from src.services import almacenamiento

    carpeta = DIRECTORIO / f"respaldo_{datetime.now():%Y%m%d_%H%M%S}"
    (carpeta / "datos").mkdir(parents=True)
    (carpeta / "archivos").mkdir()
    conn = conectar()
    conn.set_session(readonly=True)
    manifiesto = {"fecha": datetime.now().isoformat(timespec="seconds"),
                  "tablas": {}, "archivos": {}}
    try:
        cur = conn.cursor()
        for tabla in tablas_en_orden(cur):
            cur.execute(f'SELECT row_to_json(t)::text FROM "{tabla}" t')
            filas = [f[0] for f in cur.fetchall()]
            (carpeta / "datos" / f"{tabla}.jsonl").write_text(
                "\n".join(filas), encoding="utf-8"
            )
            manifiesto["tablas"][tabla] = len(filas)
        for clave in claves_de_archivos(cur):
            contenido = almacenamiento.leer(clave)
            destino = carpeta / "archivos" / clave
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido)
            manifiesto["archivos"][clave] = sha256(contenido)
    finally:
        conn.close()
    (carpeta / "manifiesto.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Respaldo: {carpeta}")
    print(f"  tablas: {len(manifiesto['tablas'])} | "
          f"filas: {sum(manifiesto['tablas'].values())} | "
          f"archivos: {len(manifiesto['archivos'])}")
    return 0


def reajustar_secuencias(cur, tablas):
    for tabla in tablas:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s", (tabla,)
        )
        for (col,) in cur.fetchall():
            cur.execute("SELECT pg_get_serial_sequence(%s, %s)",
                        (f'public."{tabla}"', col))
            seq = cur.fetchone()[0]
            if seq:
                cur.execute(
                    f'SELECT setval(%s, COALESCE(MAX("{col}"), 1), '
                    f'MAX("{col}") IS NOT NULL) FROM "{tabla}"', (seq,)
                )


def restaurar(args):
    from src.services import almacenamiento

    carpeta = Path(args.carpeta)
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    # Integridad de los archivos antes de tocar la base.
    for clave, sello in manifiesto["archivos"].items():
        if sha256((carpeta / "archivos" / clave).read_bytes()) != sello:
            raise SystemExit(f"El archivo {clave} del respaldo está alterado.")
    if not args.confirmar_reemplazo:
        raise SystemExit("Falta --confirmar-reemplazo: la restauración VACÍA las tablas.")

    conn = conectar()
    try:
        cur = conn.cursor()
        tablas = tablas_en_orden(cur)
        faltan = set(manifiesto["tablas"]) ^ set(tablas)
        if faltan:
            raise SystemExit(f"El esquema destino no coincide con el respaldo: {sorted(faltan)}")
        lista = ", ".join(f'"{t}"' for t in tablas)
        for t in tablas:
            cur.execute(f'ALTER TABLE "{t}" DISABLE TRIGGER USER')
        cur.execute(f"TRUNCATE {lista} RESTART IDENTITY CASCADE")
        for t in tablas:
            texto = (carpeta / "datos" / f"{t}.jsonl").read_text(encoding="utf-8")
            filas = [json.loads(linea) for linea in texto.splitlines() if linea]
            if filas:
                cur.execute(
                    f'INSERT INTO "{t}" SELECT * FROM '
                    f'json_populate_recordset(NULL::"{t}", %s::json)',
                    (json.dumps(filas),),
                )
        for t in tablas:
            cur.execute(f'ALTER TABLE "{t}" ENABLE TRIGGER USER')
        reajustar_secuencias(cur, tablas)
        for t in tablas:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            if cur.fetchone()[0] != manifiesto["tablas"][t]:
                raise SystemExit(f"Conteo distinto en {t}: restauración abortada.")
        print(f"[ok] {len(tablas)} tablas verificadas contra el manifiesto.")
        if args.simular:
            conn.rollback()
            print("Simulación terminada: rollback, la base quedó como estaba.")
            return 0
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

    for clave in manifiesto["archivos"]:
        almacenamiento.guardar(clave, (carpeta / "archivos" / clave).read_bytes(),
                               sobrescribir=True)
    print(f"[ok] {len(manifiesto['archivos'])} archivo(s) devueltos al repositorio.")
    print("Restauración completada.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Respaldo y restauración de SETESA.")
    parser.add_argument("--env", default=str(RAIZ / ".env.produccion"))
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("respaldar")
    r = sub.add_parser("restaurar")
    r.add_argument("carpeta")
    r.add_argument("--confirmar-reemplazo", action="store_true")
    r.add_argument("--simular", action="store_true")
    args = parser.parse_args()
    cargar_entorno(args.env)
    return respaldar(args) if args.orden == "respaldar" else restaurar(args)


if __name__ == "__main__":
    sys.exit(main())
