# Prueba funcional end-to-end del workflow SETESA contra Supabase.
# Uso: python tests/smoke_test.py
#
# Verifica el flujo completo (registro -> coordinador -> gerencia), el
# historial de estados, las transiciones inválidas, el CHECK de la base,
# la generación del PDF y el historial del consultor. Limpia sus propios datos.

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import io
from uuid import uuid4

import psycopg2
from PIL import Image

from src.core.database import get_connection
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
    estado_valido,
    puede_transicionar,
    siguiente_estado,
)
from src.core.security import hash_password
from src.core.utils import calcular_dias_habiles
from src.core.reportes import exportar_csv, filtrar_solicitudes
from src.core.feriados import (
    crear_feriado,
    eliminar_feriado,
    fechas_feriados,
    listar_feriados,
)
from src.core.usuarios import listar_coordinadores
from src.core.vacaciones import obtener_saldo_vacaciones
from src.core.validaciones import ValidacionError
from src.core.solicitudes import (
    TransicionInvalida,
    cambiar_estado,
    obtener_estado,
    obtener_historial,
    obtener_solicitud,
    registrar_solicitud,
)
from src.core.vigencia import (
    ejecutar_depuracion,
    obtener_inactivos,
    reactivar_usuario,
    registrar_actividad,
    usuario_activo,
)
from src.features.registro import registrar_solicitud_firmada, obtener_mis_solicitudes
from src.features.dashboard import obtener_solicitudes
from src.services.documentos import generar_pdf_solicitud, preparar_pdf_descarga
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
    sabado = datetime.date(2026, 10, 17)
    domingo = datetime.date(2026, 10, 18)
    check("calcular_dias_habiles (fin de semana)",
          calcular_dias_habiles(sabado, domingo) == 0)


def test_transiciones_unitarias():
    check("transición Ingresada -> Pendiente Firma Coordinador",
          puede_transicionar(ESTADO_INGRESADA, ESTADO_PENDIENTE_FIRMA_COORDINADOR))
    check("transición Ingresada -> Finalizada rechazada",
          not puede_transicionar(ESTADO_INGRESADA, ESTADO_FINALIZADA))
    check("siguiente estado de Gerencia es Finalizada",
          siguiente_estado(ESTADO_PENDIENTE_APROBACION_GERENCIA) == ESTADO_FINALIZADA)
    check("estado legado fuera de catálogo",
          not estado_valido("En revisión por jefe inmediato GTC"))


def test_conectividad():
    conn = get_connection()
    if not conn:
        check("conexión a Supabase", False, "-> get_connection() devolvió None")
        return conn
    try:
        cursor = conn.cursor()
        for tabla in ("rol", "usuario", "solicitud", "solicitud_historial"):
            cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
            total = cursor.fetchone()[0]
            check(f"tabla '{tabla}' accesible", True, f"-> {total} filas")
        cursor.close()
    except Exception as e:
        check("esquema accesible", False, f"-> {e}")
    return conn


def _ids_por_rol(conn):
    cursor = conn.cursor()
    ids = {}
    for rol in ("Consultor", "Coordinador GTC", "Administrador"):
        cursor.execute(
            """
            SELECT u.id_usuario FROM usuario u
            JOIN rol r ON u.id_rol = r.id_rol
            WHERE r.nombre_rol = %s AND u.estado_vigencia = TRUE
            ORDER BY u.id_usuario LIMIT 1
            """,
            (rol,),
        )
        fila = cursor.fetchone()
        ids[rol] = fila[0] if fila else None
    cursor.close()
    return ids


def test_workflow_end_to_end(conn):
    """Registro -> coordinador -> gerencia, con historial y transición inválida."""
    if not conn:
        check("workflow end-to-end", False, "-> sin conexión")
        return

    ids = _ids_por_rol(conn)
    id_consultor = ids.get("Consultor")
    id_coordinador = ids.get("Coordinador GTC")
    id_admin = ids.get("Administrador")
    if not all((id_consultor, id_coordinador, id_admin)):
        check("workflow end-to-end", False, "-> faltan usuarios por rol")
        return

    marca = f"TEST_WORKFLOW_{uuid4().hex[:8]}"
    id_solicitud = None
    try:
        id_solicitud = registrar_solicitud(
            id_consultor, "VACACION",
            datetime.date(2026, 10, 12), datetime.date(2026, 10, 16),
            "Jefe GTC", "Consultor", "C-001", 5, marca, firma_dummy_b64(),
        )
        check("1) Registro transaccional", id_solicitud is not None,
              f"-> id={id_solicitud}")
        check("2) Estado posterior al registro",
              obtener_estado(id_solicitud) == ESTADO_PENDIENTE_FIRMA_COORDINADOR,
              f"-> {obtener_estado(id_solicitud)}")

        historial = obtener_historial(id_solicitud)
        check("3) Historial registra Ingresada y Pendiente Firma",
              len(historial) == 2 and set(historial["estado_nuevo"]) == {
                  ESTADO_INGRESADA, ESTADO_PENDIENTE_FIRMA_COORDINADOR,
              },
              f"-> {len(historial)} movimientos")

        anterior, nuevo = cambiar_estado(
            id_solicitud, ESTADO_PENDIENTE_APROBACION_GERENCIA,
            id_coordinador, "Visto bueno de prueba.", firma_b64=firma_dummy_b64(),
        )
        check("4) Coordinador firma -> Pendiente Gerencia",
              (anterior, nuevo) == (
                  ESTADO_PENDIENTE_FIRMA_COORDINADOR,
                  ESTADO_PENDIENTE_APROBACION_GERENCIA,
              ))

        try:
            cambiar_estado(
                id_solicitud, ESTADO_PENDIENTE_FIRMA_COORDINADOR, id_admin
            )
            check("5) Transición inválida rechazada", False, "-> no lanzó error")
        except TransicionInvalida:
            check("5) Transición inválida rechazada", True)

        cambiar_estado(
            id_solicitud, ESTADO_FINALIZADA, id_admin, "Cierre de prueba.",
            firma_b64=firma_dummy_b64(),
        )
        check("6) Gerencia finaliza", obtener_estado(id_solicitud) == ESTADO_FINALIZADA)

        datos = obtener_solicitud(id_solicitud)
        check("7) Firmas de coordinador y gerencia persistidas",
              bool(datos["firma_jefe_gtc"]) and bool(datos["firma_gerencia"]))

        historial = obtener_historial(id_solicitud)
        check("8) Historial completo (4 movimientos)", len(historial) == 4,
              f"-> {len(historial)} movimientos")
    except Exception as e:
        check("workflow end-to-end", False, f"-> {e}")
    finally:
        if id_solicitud:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM solicitud WHERE id_solicitud = %s", (id_solicitud,)
            )
            conn.commit()
            cursor.execute(
                "SELECT COUNT(*) FROM solicitud_historial WHERE id_solicitud = %s",
                (id_solicitud,),
            )
            restantes = cursor.fetchone()[0]
            cursor.close()
            check("9) Historial eliminado en cascada", restantes == 0)
            print("   (datos de prueba del workflow eliminados)")


def test_check_estado(conn):
    """El CHECK de PostgreSQL debe impedir estados fuera del catálogo."""
    if not conn:
        check("CHECK de estado_workflow", False, "-> sin conexión")
        return
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id_solicitud FROM solicitud LIMIT 1")
        fila = cursor.fetchone()
        if not fila:
            check("CHECK de estado_workflow", False, "-> no hay solicitudes")
            return
        id_solicitud = fila[0]
        cursor.execute("SAVEPOINT sp_check_estado")
        try:
            cursor.execute(
                "UPDATE solicitud SET estado_workflow = %s WHERE id_solicitud = %s",
                ("Estado Invalido", id_solicitud),
            )
            check("CHECK de estado_workflow", False, "-> aceptó un estado inválido")
        except psycopg2.Error:
            cursor.execute("ROLLBACK TO SAVEPOINT sp_check_estado")
            check("CHECK de estado_workflow", True)
        finally:
            conn.rollback()
    finally:
        cursor.close()


def test_pdf():
    ruta = None
    try:
        ruta = generar_pdf_accion_personal(
            "QA Test", "Jefe GTC", "Consultor", "C-001", "VACACION",
            "2026-10-12", "2026-10-16", 5, "Prueba de generación",
            ESTADO_FINALIZADA,
            firma_empleado_b64=firma_dummy_b64(),
            firma_jefe_b64=firma_dummy_b64(),
            firma_gerencia_b64=firma_dummy_b64(),
            id_solicitud=999_999_999,
        )
        existe = Path(ruta).exists()
        ubicado = "storage" in Path(ruta).parts
        check("generación de PDF", existe, f"-> {ruta}")
        check("PDF en storage/pdf", ubicado)
        contenido = Path(ruta).read_bytes()
        imagenes = contenido.count(b"/Subtype /Image")
        check("PDF con las 3 firmas estampadas", imagenes == 3,
              f"-> {imagenes} imágenes")
    except Exception as e:
        check("generación de PDF", False, f"-> {e}")
    finally:
        if ruta and Path(ruta).exists():
            Path(ruta).unlink()


def test_consultor_flujo():
    """Registro del consultor -> historial -> PDF, con limpieza posterior."""
    conn = get_connection()
    if not conn:
        check("consultor: registro e historial", False, "-> sin conexión")
        return
    marca = f"TEST_CONSULTOR_{uuid4().hex[:8]}"
    pdf_generado = []
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

        id_solicitud = registrar_solicitud_firmada(
            id_usuario, "VACACION", datetime.date(2026, 10, 12),
            datetime.date(2026, 10, 16), "Jefe GTC", "Consultor", "C-001",
            5, marca, firma_dummy_b64(),
        )
        check("consultor: registrar_solicitud_firmada", id_solicitud is not None)

        df = obtener_mis_solicitudes(id_usuario)
        presente = (not df.empty) and bool((df["explicacion"] == marca).any())
        check("consultor: el historial incluye la nueva solicitud", presente)

        if presente:
            fila = df[df["explicacion"] == marca].iloc[0]
            check(
                "consultor: estado Pendiente de Firma Coordinador",
                fila["estado_workflow"] == ESTADO_PENDIENTE_FIRMA_COORDINADOR,
            )
            ruta = generar_pdf_solicitud(id_solicitud)
            check("consultor: PDF del expediente", Path(ruta).exists(), f"-> {ruta}")
            datos = obtener_solicitud(id_solicitud)
            check("consultor: ruta_pdf persistida", datos["ruta_pdf"] == ruta)
            pdf_generado.append(ruta)
    except Exception as e:
        check("consultor: registro e historial", False, f"-> {e}")
    finally:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM solicitud WHERE explicacion = %s", (marca,))
        conn.commit()
        cursor.close()
        conn.close()
        for ruta in pdf_generado:
            Path(ruta).unlink(missing_ok=True)
        print("   (datos de prueba del consultor eliminados)")


def test_dashboard_gerencia():
    """Repositorio, filtros, CSV y descarga del PDF final (RF-04 / HU-03)."""
    conn = get_connection()
    if not conn:
        check("dashboard: repositorio y descarga", False, "-> sin conexión")
        return

    ids = _ids_por_rol(conn)
    id_consultor = ids.get("Consultor")
    id_coordinador = ids.get("Coordinador GTC")
    id_admin = ids.get("Administrador")
    if not all((id_consultor, id_coordinador, id_admin)):
        check("dashboard: repositorio y descarga", False, "-> faltan usuarios")
        conn.close()
        return

    marca = f"TEST_DASHBOARD_{uuid4().hex[:8]}"
    id_solicitud = None
    ruta_pdf = None
    try:
        id_solicitud = registrar_solicitud(
            id_consultor, "VACACION",
            datetime.date(2030, 1, 7), datetime.date(2030, 1, 11),
            "Jefe GTC", "Consultor", "C-001", 5, marca, firma_dummy_b64(),
        )
        cambiar_estado(
            id_solicitud, ESTADO_PENDIENTE_APROBACION_GERENCIA,
            id_coordinador, "Firma de prueba.", firma_b64=firma_dummy_b64(),
        )
        cambiar_estado(
            id_solicitud, ESTADO_FINALIZADA, id_admin, "Cierre de prueba.",
            firma_b64=firma_dummy_b64(),
        )

        df = obtener_solicitudes()
        check("dashboard: el repositorio incluye el expediente",
              id_solicitud in set(df["id_solicitud"].tolist()))
        check("dashboard: columnas para filtros y descarga",
              {"fecha_inicio", "fecha_fin", "tipo_ausencia", "ruta_pdf"}
              <= set(df.columns))

        nombre = df.loc[
            df["id_solicitud"] == id_solicitud, "nombre_completo"
        ].iloc[0]
        df_filtrado = filtrar_solicitudes(
            df,
            nombre=nombre,
            estado=ESTADO_FINALIZADA,
            tipo="VACACION",
            fecha_desde=datetime.date(2030, 1, 1),
            fecha_hasta=datetime.date(2030, 1, 31),
        )
        check("dashboard: filtros combinados (nombre, estado, tipo y fecha)",
              id_solicitud in set(df_filtrado["id_solicitud"].tolist()))

        csv = exportar_csv(df_filtrado).decode("utf-8-sig")
        check("dashboard: exportación CSV incluye el expediente",
              str(id_solicitud) in csv and nombre in csv)

        ruta_pdf, contenido = preparar_pdf_descarga(id_solicitud)
        check("dashboard: PDF final descargable con 3 firmas",
              contenido.startswith(b"%PDF")
              and contenido.count(b"/Subtype /Image") == 3,
              f"-> {Path(ruta_pdf).name}")
    except Exception as e:
        check("dashboard: repositorio y descarga", False, f"-> {e}")
    finally:
        if ruta_pdf:
            Path(ruta_pdf).unlink(missing_ok=True)
        if id_solicitud:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM solicitud WHERE id_solicitud = %s", (id_solicitud,)
            )
            conn.commit()
            cursor.close()
        conn.close()
        print("   (datos de prueba del dashboard eliminados)")


def test_vacaciones_feriados():
    """RF-01: saldo de vacaciones, feriados y validaciones de servidor."""
    conn = get_connection()
    if not conn:
        check("vacaciones y feriados", False, "-> sin conexión")
        return

    ids = _ids_por_rol(conn)
    id_consultor = ids.get("Consultor")
    if not id_consultor:
        check("vacaciones y feriados", False, "-> no hay consultores")
        conn.close()
        return

    fecha_feriado = datetime.date(2099, 8, 15)
    id_feriado = None
    id_solicitud = None
    try:
        # Feriados sembrados y exclusión del conteo.
        df_feriados = listar_feriados(2026)
        check(
            "feriados: semilla 2026 incluye Navidad",
            datetime.date(2026, 12, 25) in set(df_feriados["fecha"].tolist()),
        )
        feriados_navidad = fechas_feriados(
            datetime.date(2026, 12, 24), datetime.date(2026, 12, 28)
        )
        check(
            "feriados: se excluyen del cálculo de días hábiles",
            datetime.date(2026, 12, 25) in feriados_navidad
            and calcular_dias_habiles(
                datetime.date(2026, 12, 24),
                datetime.date(2026, 12, 28),
                feriados_navidad,
            )
            == 2,
        )

        # CRUD temporal del catálogo.
        id_feriado = crear_feriado(fecha_feriado, "Feriado smoke")
        check(
            "feriados: alta y consulta por rango",
            fecha_feriado
            in fechas_feriados(fecha_feriado, fecha_feriado),
        )
        check("feriados: baja del catálogo", eliminar_feriado(id_feriado) is True)
        id_feriado = None

        # Saldo de vacaciones (año 2031, sin datos previos).
        saldo_inicial = obtener_saldo_vacaciones(id_consultor, anio=2031)
        check(
            "vacaciones: saldo = asignados - usados",
            saldo_inicial["disponibles"]
            == saldo_inicial["asignados"] - saldo_inicial["usados"],
            f"-> {saldo_inicial}",
        )

        id_solicitud = registrar_solicitud(
            id_consultor,
            "VACACION",
            datetime.date(2031, 1, 6),
            datetime.date(2031, 1, 7),
            "Jefe GTC",
            "Consultor",
            "C-001",
            2,
            f"TEST_VACACIONES_{uuid4().hex[:8]}",
            firma_dummy_b64(),
        )
        saldo_despues = obtener_saldo_vacaciones(id_consultor, anio=2031)
        check(
            "vacaciones: el registro descuenta los días",
            saldo_despues["usados"] == saldo_inicial["usados"] + 2,
            f"-> usados={saldo_despues['usados']}",
        )

        try:
            registrar_solicitud(
                id_consultor,
                "VACACION",
                datetime.date(2031, 2, 3),
                datetime.date(2031, 2, 28),
                "Jefe GTC",
                "Consultor",
                "C-001",
                20,
                f"TEST_EXCESO_{uuid4().hex[:8]}",
                firma_dummy_b64(),
            )
        except ValidacionError:
            check("vacaciones: saldo insuficiente rechazado", True)
        else:
            check("vacaciones: saldo insuficiente rechazado", False)

        try:
            registrar_solicitud(
                id_consultor,
                "DUELO",
                datetime.date(2031, 3, 10),
                datetime.date(2031, 3, 9),
                "Jefe GTC",
                "Consultor",
                "C-001",
                1,
                f"TEST_FECHAS_{uuid4().hex[:8]}",
                firma_dummy_b64(),
            )
        except ValidacionError:
            check("validación: fechas invertidas rechazadas", True)
        else:
            check("validación: fechas invertidas rechazadas", False)

        coordinadores = listar_coordinadores()
        check(
            "jefe GTC: se selecciona desde usuarios del rol",
            not coordinadores.empty
            and "nombre_completo" in coordinadores.columns,
            f"-> {len(coordinadores)} coordinador(es)",
        )
    except Exception as e:
        check("vacaciones y feriados", False, f"-> {e}")
    finally:
        if id_feriado is not None:
            try:
                eliminar_feriado(id_feriado)
            except Exception:
                pass
        cursor = conn.cursor()
        if id_solicitud:
            cursor.execute(
                "DELETE FROM solicitud WHERE id_solicitud = %s", (id_solicitud,)
            )
        cursor.execute(
            "DELETE FROM solicitud WHERE explicacion LIKE 'TEST_VACACIONES_%' "
            "OR explicacion LIKE 'TEST_EXCESO_%' "
            "OR explicacion LIKE 'TEST_FECHAS_%'"
        )
        conn.commit()
        cursor.close()
        conn.close()
        print("   (datos de prueba de vacaciones y feriados eliminados)")


def test_vigencia():
    """Baja lógica semestral, auditoría y reactivación, con limpieza posterior."""
    conn = get_connection()
    if not conn:
        check("vigencia: depuración semestral", False, "-> sin conexión")
        return

    marca = uuid4().hex[:8]
    ids = {}
    max_log = 0
    snapshot = {}
    preparado = False
    try:
        cursor = conn.cursor()
        ids_roles = _ids_por_rol(conn)
        id_admin = ids_roles.get("Administrador")
        if not id_admin:
            check("vigencia: depuración semestral", False,
                  "-> no hay Administrador vigente")
            return

        cursor.execute("SELECT COALESCE(MAX(id_log), 0) FROM vigencia_log")
        max_log = cursor.fetchone()[0]

        cursor.execute("SELECT id_usuario, estado_vigencia FROM usuario")
        snapshot = dict(cursor.fetchall())
        preparado = True

        cursor.execute(
            """
            SELECT id_rol FROM rol WHERE nombre_rol = 'Consultor'
            """
        )
        id_rol_consultor = cursor.fetchone()[0]

        # "vencido" supera los 6 meses; "reciente" no debe tocarse.
        for clave, intervalo in (("vencido", "7 months"), ("reciente", "1 day")):
            correo = f"pytest_vigencia_smoke_{clave}_{marca}@example.com"
            cursor.execute(
                """
                INSERT INTO usuario
                    (id_rol, nombre_completo, correo_institucional,
                     password_hash, estado_vigencia, ultima_actividad)
                VALUES (%s, %s, %s, %s, TRUE, NOW() - %s::interval)
                RETURNING id_usuario
                """,
                (id_rol_consultor, f"SMOKE {clave} {marca}", correo,
                 hash_password("ClaveSmoke123"), intervalo),
            )
            ids[clave] = cursor.fetchone()[0]
        conn.commit()

        df = obtener_inactivos(id_excluido=id_admin)
        candidatos = set(df["id_usuario"].tolist())
        check("vigencia: candidato con más de 6 meses",
              ids["vencido"] in candidatos)
        check("vigencia: usuario reciente no es candidato",
              ids["reciente"] not in candidatos)
        check("vigencia: Administrador nunca es candidato",
              id_admin not in candidatos)

        df_afectados, id_log = ejecutar_depuracion(id_ejecutor=id_admin)
        afectados = set(df_afectados["id_usuario"].tolist())
        check("vigencia: depuración aplica baja lógica",
              ids["vencido"] in afectados and usuario_activo(ids["vencido"]) is False)
        check("vigencia: usuario reciente sigue vigente",
              ids["reciente"] not in afectados and usuario_activo(ids["reciente"]) is True)

        cursor.execute(
            """
            SELECT accion, usuarios_afectados, id_ejecutor, detalle
            FROM vigencia_log WHERE id_log = %s
            """,
            (id_log,),
        )
        accion, afectados_log, ejecutor, detalle = cursor.fetchone()
        check("vigencia: ejecución auditada",
              accion == "DEPURACION" and ejecutor == id_admin
              and afectados_log == len(df_afectados),
              f"-> log={id_log}, afectados={afectados_log}")
        check("vigencia: detalle del log incluye al usuario",
              str(ids["vencido"]) in detalle)

        check("vigencia: registrar_actividad actualiza la fecha",
              registrar_actividad(ids["reciente"]) is True)

        id_log_reac = reactivar_usuario(ids["vencido"], id_ejecutor=id_admin)
        check("vigencia: reactivación devuelve vigencia",
              usuario_activo(ids["vencido"]) is True)
        cursor.execute(
            "SELECT accion FROM vigencia_log WHERE id_log = %s", (id_log_reac,)
        )
        check("vigencia: reactivación auditada",
              cursor.fetchone()[0] == "REACTIVACION")
        cursor.close()
    except Exception as e:
        check("vigencia: depuración semestral", False, f"-> {e}")
    finally:
        cursor = conn.cursor()
        try:
            for id_usuario, estado in snapshot.items():
                cursor.execute(
                    "UPDATE usuario SET estado_vigencia = %s WHERE id_usuario = %s",
                    (estado, id_usuario),
                )
            if preparado:
                cursor.execute(
                    "DELETE FROM vigencia_log WHERE id_log > %s", (max_log,)
                )
            if ids:
                cursor.execute(
                    "DELETE FROM usuario WHERE id_usuario = ANY(%s)",
                    (list(ids.values()),),
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        print("   (datos de prueba de vigencia eliminados)")


if __name__ == "__main__":
    print("=== SMOKE TEST SETESA ===\n")
    test_dias_habiles()
    test_transiciones_unitarias()
    conn = test_conectividad()
    test_workflow_end_to_end(conn)
    test_check_estado(conn)
    if conn:
        conn.close()
    test_pdf()
    test_consultor_flujo()
    test_dashboard_gerencia()
    test_vacaciones_feriados()
    test_vigencia()

    fallidos = [r for r in resultados if r[0] == "FAIL"]
    print(f"\n=== RESUMEN: {len(resultados) - len(fallidos)}/{len(resultados)} OK ===")
    sys.exit(1 if fallidos else 0)
