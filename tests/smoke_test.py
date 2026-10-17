# Prueba funcional end-to-end del workflow SETESA contra Supabase.
# Uso: python tests/smoke_test.py
#
# La prueba de workflow se ejecuta dentro de una transacción con ROLLBACK:
# verifica la secuencia de estados sin dejar datos de prueba en la base.

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import io
from uuid import uuid4

from PIL import Image

from src.core.database import get_connection
from src.core.workflow import (
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_FINALIZADA,
)
from src.core.utils import calcular_dias_habiles
from src.features.registro import registrar_solicitud_firmada, obtener_mis_solicitudes
from src.services.motor_pdf import generar_pdf_accion_personal

resultados = []


def check(nombre, condicion, detalle=""):
    estado = "PASS" if condicion else "FAIL"
    resultados.append((estado, nombre, detalle))
    print(f"[{estado}] {nombre} {detalle}")


def firma_dummy_b64():
    img = Image.new("RGB", (120, 40), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_dias_habiles():
    inicio = datetime.date(2026, 10, 12)  # lunes
    fin = datetime.date(2026, 10, 16)     # viernes
    check("calcular_dias_habiles (lun-vie)", calcular_dias_habiles(inicio, fin) == 5,
          f"-> {calcular_dias_habiles(inicio, fin)}")


def test_conectividad():
    conn = get_connection()
    if not conn:
        check("conexión a Supabase", False, "-> get_connection() devolvió None")
        return conn
    try:
        cursor = conn.cursor()
        for tabla in ("rol", "usuario", "solicitud"):
            cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
            total = cursor.fetchone()[0]
            check(f"tabla '{tabla}' accesible", True, f"-> {total} filas")
        cursor.close()
    except Exception as e:
        check("esquema accesible", False, f"-> {e}")
    return conn


def test_workflow_transaccional(conn):
    if not conn:
        check("workflow end-to-end", False, "-> sin conexión")
        return
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id_usuario FROM usuario LIMIT 1")
        row = cursor.fetchone()
        if not row:
            check("workflow end-to-end", False, "-> no hay usuarios")
            return
        id_usuario = row[0]

        # 1. Consultor registra -> 'Ingresada'
        cursor.execute(
            """
            INSERT INTO solicitud
                (id_usuario, tipo_ausencia, fecha_inicio, fecha_fin, estado_workflow,
                 jefe_gtc, puesto, codigo_empleado, dias_solicitados, explicacion, firma_empleado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_solicitud
            """,
            (id_usuario, "VACACION", "2026-10-12", "2026-10-16", ESTADO_INGRESADA,
             "Jefe GTC", "Consultor", "C-001", 5, "Prueba E2E", firma_dummy_b64()),
        )
        id_solicitud = cursor.fetchone()[0]
        check("1) Consultor registra solicitud", True, f"-> id={id_solicitud} [{ESTADO_INGRESADA}]")

        # 2. Coordinador ve pendientes ('Ingresada') y firma -> 'Pendiente de Aprobación Gerencia'
        cursor.execute(
            "SELECT COUNT(*) FROM solicitud WHERE estado_workflow = %s AND id_solicitud = %s",
            (ESTADO_INGRESADA, id_solicitud),
        )
        visible = cursor.fetchone()[0] == 1
        check("2) Coordinador ve la solicitud 'Ingresada'", visible)

        cursor.execute(
            "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
            (ESTADO_PENDIENTE_APROBACION_GERENCIA, id_solicitud),
        )
        check("3) Coordinador firma -> 'Pendiente de Aprobación Gerencia'",
              cursor.rowcount == 1)

        # 4. Gerencia aprueba -> 'Finalizada'
        cursor.execute(
            "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
            (ESTADO_FINALIZADA, id_solicitud),
        )
        check("4) Gerencia aprueba -> 'Finalizada'", cursor.rowcount == 1)

        cursor.execute("SELECT estado_workflow FROM solicitud WHERE id_solicitud = %s",
                       (id_solicitud,))
        check("5) Estado final persistido", cursor.fetchone()[0] == ESTADO_FINALIZADA)
    except Exception as e:
        check("workflow end-to-end", False, f"-> {e}")
    finally:
        conn.rollback()  # No persiste datos de prueba
        cursor.close()
        print("   (transacción revertida: la base quedó intacta)")


def test_pdf():
    try:
        ruta = generar_pdf_accion_personal(
            "QA Test", "Jefe GTC", "Consultor", "C-001", "VACACION",
            "2026-10-12", "2026-10-16", 5, "Prueba de generación",
            ESTADO_FINALIZADA,
            firma_empleado_b64=firma_dummy_b64(),
            firma_jefe_b64=firma_dummy_b64(),
            firma_gerencia_b64=firma_dummy_b64(),
        )
        existe = Path(ruta).exists()
        ubicado = "storage" in Path(ruta).parts
        check("generación de PDF", existe, f"-> {ruta}")
        check("PDF en storage/pdf", ubicado)
    except Exception as e:
        check("generación de PDF", False, f"-> {e}")


def test_consultor_flujo():
    """Registro del consultor -> historial -> PDF, con limpieza posterior."""
    conn = get_connection()
    if not conn:
        check("consultor: registro e historial", False, "-> sin conexión")
        return
    marca = f"TEST_CONSULTOR_{uuid4().hex[:8]}"
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.id_usuario FROM usuario u
            JOIN rol r ON u.id_rol = r.id_rol
            WHERE r.nombre_rol = 'Consultor'
            ORDER BY u.id_usuario LIMIT 1
            """
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            check("consultor: registro e historial", False, "-> no hay consultores")
            return
        id_usuario = row[0]

        ok = registrar_solicitud_firmada(
            id_usuario, "VACACION", datetime.date(2026, 10, 12), datetime.date(2026, 10, 16),
            "Jefe GTC", "Consultor", "C-001", 5, marca, firma_dummy_b64(),
        )
        check("consultor: registrar_solicitud_firmada", ok)

        df = obtener_mis_solicitudes(id_usuario)
        presente = (not df.empty) and bool((df["explicacion"] == marca).any())
        check("consultor: el historial incluye la nueva solicitud", presente)

        if presente:
            fila = df[df["explicacion"] == marca].iloc[0]
            ruta = generar_pdf_accion_personal(
                "QA Consultor", fila["jefe_gtc"], fila["puesto"], fila["codigo_empleado"],
                fila["tipo_ausencia"], str(fila["fecha_inicio"]), str(fila["fecha_fin"]),
                fila["dias_solicitados"], fila["explicacion"], fila["estado_workflow"],
                firma_empleado_b64=fila.get("firma_empleado"),
            )
            check("consultor: PDF del expediente", Path(ruta).exists(), f"-> {ruta}")
    except Exception as e:
        check("consultor: registro e historial", False, f"-> {e}")
    finally:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM solicitud WHERE explicacion = %s", (marca,))
        conn.commit()
        cursor.close()
        conn.close()
        print("   (datos de prueba del consultor eliminados)")


if __name__ == "__main__":
    print("=== SMOKE TEST SETESA ===\n")
    test_dias_habiles()
    conn = test_conectividad()
    test_workflow_transaccional(conn)
    if conn:
        conn.close()
    test_pdf()
    test_consultor_flujo()

    fallidos = [r for r in resultados if r[0] == "FAIL"]
    print(f"\n=== RESUMEN: {len(resultados) - len(fallidos)}/{len(resultados)} OK ===")
    sys.exit(1 if fallidos else 0)
