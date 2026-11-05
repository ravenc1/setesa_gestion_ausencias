# Fase 25: retiro de solicitudes por el consultor y avisos por correo del flujo.

import datetime
import os
from pathlib import Path
from uuid import uuid4

import pytest

from src.core import avisos_flujo, workflow

requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)

RAIZ = Path(__file__).resolve().parents[1]
FIRMA = "ZmlybWE="  # cualquier texto base64: el cifrado no valida la imagen


# ---------------------------------------------------------------------------
# Reglas del workflow
# ---------------------------------------------------------------------------
def test_solo_se_retira_antes_del_visto_bueno_del_banco():
    assert workflow.puede_retirar(workflow.ESTADO_INGRESADA)
    assert workflow.puede_retirar(workflow.ESTADO_PENDIENTE_FIRMA_COORDINADOR)
    assert not workflow.puede_retirar(workflow.ESTADO_PENDIENTE_APROBACION_GERENCIA)
    assert not workflow.puede_retirar(workflow.ESTADO_FINALIZADA)
    assert workflow.RESOLUCION_RETIRADA in workflow.RESOLUCIONES


# ---------------------------------------------------------------------------
# Contenido de los avisos
# ---------------------------------------------------------------------------
DATOS = {
    "id_solicitud": 77,
    "tipo_ausencia": "VACACION",
    "fecha_inicio": datetime.date(2037, 3, 2),
    "fecha_fin": datetime.date(2037, 3, 4),
    "resolucion": "Denegada",
    "id_coordinador": 1,
    "id_usuario": 2,
    "nombre_completo": "Ana Pérez",
}


@pytest.mark.parametrize("evento", avisos_flujo.EVENTOS)
def test_cada_aviso_dice_que_paso_sin_datos_sensibles(evento):
    datos = {**DATOS, "explicacion": "SECRETO-MEDICO", "motivo_resolucion": "SECRETO-MOTIVO"}
    asunto, cuerpo = avisos_flujo.construir_aviso(evento, datos, "Luis")
    assert "77" in asunto
    assert "Hola Luis," in cuerpo and "Ana Pérez" in cuerpo
    assert "02/03/2037" in cuerpo and "04/03/2037" in cuerpo
    assert "SECRETO" not in asunto + cuerpo


def test_un_evento_desconocido_no_se_acepta():
    with pytest.raises(ValueError):
        avisos_flujo.construir_aviso("OTRO", DATOS)


def test_sin_correo_configurado_o_deshabilitado_no_se_envia_nada(monkeypatch):
    enviados = []
    monkeypatch.delenv("SETESA_SIN_CORREO", raising=False)
    monkeypatch.setattr(avisos_flujo, "configuracion_smtp", lambda: None)
    assert avisos_flujo.avisar("NUEVA", 1, enviar=lambda *a, **k: enviados.append(a)) == 0
    monkeypatch.setenv("SETESA_SIN_CORREO", "1")
    assert avisos_flujo.avisar("NUEVA", 1, enviar=lambda *a, **k: enviados.append(a)) == 0
    assert avisos_flujo.avisar_en_segundo_plano("NUEVA", 1) is None
    assert enviados == []


def test_un_error_al_preparar_el_aviso_no_rompe_el_flujo(monkeypatch):
    monkeypatch.delenv("SETESA_SIN_CORREO", raising=False)
    monkeypatch.setattr(avisos_flujo, "configuracion_smtp", lambda: {"x": 1})

    def falla():
        raise RuntimeError("base caída")

    monkeypatch.setattr(avisos_flujo, "get_connection", falla)
    assert avisos_flujo.avisar("NUEVA", 1) == 0  # no lanza


# ---------------------------------------------------------------------------
# Con base de datos (todo en una transacción que se revierte)
# ---------------------------------------------------------------------------
@pytest.fixture
def mundo(monkeypatch):
    from scripts.migracion_fase25 import DDL
    from src.core import evidencias, feriados, recordatorios, solicitudes, vacaciones, vigencia
    from src.core.security import hash_password
    from transaccion import transaccion_revertida

    triggers = (RAIZ / "docs" / "triggers.sql").read_text(encoding="utf-8")
    modulos = (solicitudes, vacaciones, feriados, vigencia, recordatorios, evidencias, avisos_flujo)
    with transaccion_revertida(monkeypatch, *modulos, ddl=[*DDL, triggers]) as cursor:
        def crear(rol, nombre):
            correo = f"pytest_{rol.lower()}_{uuid4().hex[:8]}@example.com"
            cursor.execute(
                """
                INSERT INTO usuario (id_rol, nombre_completo, correo_institucional,
                                     password_hash, estado_vigencia, ultima_actividad)
                SELECT id_rol, %s, %s, %s, TRUE, NOW() FROM rol WHERE nombre_rol = %s
                RETURNING id_usuario
                """,
                (nombre, correo, hash_password("Clave12345"), rol),
            )
            return {"id": cursor.fetchone()[0], "correo": correo}

        yield {
            "cursor": cursor,
            "consultor": crear("Consultor", "PYTEST Consultor"),
            "coordinador": crear("Coordinador GTC", "PYTEST Coordinador"),
            "gerencia": crear("Administrador", "PYTEST Gerencia"),
            "contabilidad": crear("Contabilidad", "PYTEST Contabilidad"),
            "solicitudes": solicitudes,
            "vacaciones": vacaciones,
        }


def _registrar(m, tipo="VACACION", dias=3):
    inicio = datetime.date(2037, 3, 2)  # lunes
    return m["solicitudes"].registrar_solicitud(
        m["consultor"]["id"], tipo, inicio, inicio + datetime.timedelta(days=dias - 1),
        m["coordinador"]["id"], "Consultor Técnico", "C-0147", dias,
        "Explicación privada.", FIRMA,
    )


def _estado(m, id_sol):
    m["cursor"].execute(
        "SELECT estado_workflow, resolucion, id_resuelve FROM solicitud WHERE id_solicitud = %s",
        (id_sol,),
    )
    return m["cursor"].fetchone()


@requiere_bd
def test_el_consultor_retira_su_solicitud_y_los_dias_vuelven(mundo):
    m, s = mundo, mundo["solicitudes"]
    antes = m["vacaciones"].obtener_saldo_vacaciones(m["consultor"]["id"], anio=2037)["disponibles"]
    id_sol = _registrar(m)
    assert m["vacaciones"].obtener_saldo_vacaciones(m["consultor"]["id"], anio=2037)["disponibles"] == antes - 3

    anterior = s.retirar_solicitud(id_sol, m["consultor"]["id"], "Me equivoqué en las fechas.")

    assert anterior == workflow.ESTADO_PENDIENTE_FIRMA_COORDINADOR
    assert _estado(m, id_sol) == ("Finalizada", "Retirada", m["consultor"]["id"])
    assert m["vacaciones"].obtener_saldo_vacaciones(m["consultor"]["id"], anio=2037)["disponibles"] == antes
    # El motivo queda cifrado y el historial registra el retiro.
    m["cursor"].execute("SELECT motivo_resolucion FROM solicitud WHERE id_solicitud = %s", (id_sol,))
    assert "equivoqué" not in m["cursor"].fetchone()[0]
    m["cursor"].execute(
        "SELECT estado_nuevo, observacion FROM solicitud_historial "
        "WHERE id_solicitud = %s ORDER BY id_historial DESC LIMIT 1", (id_sol,))
    estado_nuevo, observacion = m["cursor"].fetchone()
    assert estado_nuevo == "Finalizada" and "retirada" in observacion.lower()
    # No avisa a Contabilidad ni al consultor como si fuera una resolución.
    m["cursor"].execute("SELECT COUNT(*) FROM notificacion WHERE id_solicitud = %s", (id_sol,))
    assert m["cursor"].fetchone()[0] == 0


@requiere_bd
def test_el_retiro_exige_motivo_y_ser_el_dueno(mundo):
    m, s = mundo, mundo["solicitudes"]
    id_sol = _registrar(m)
    with pytest.raises(s.MotivoRequerido):
        s.retirar_solicitud(id_sol, m["consultor"]["id"], "corto")
    with pytest.raises(s.NoEsDuenoSolicitud):
        s.retirar_solicitud(id_sol, m["coordinador"]["id"], "Intento ajeno a la solicitud.")
    with pytest.raises(s.SolicitudNoEncontrada):
        s.retirar_solicitud(2_000_000_000, m["consultor"]["id"], "No existe esta solicitud.")
    assert _estado(m, id_sol)[0] == workflow.ESTADO_PENDIENTE_FIRMA_COORDINADOR


@requiere_bd
def test_no_se_retira_lo_que_ya_tiene_visto_bueno_ni_lo_finalizado(mundo):
    m, s = mundo, mundo["solicitudes"]
    id_sol = _registrar(m)
    s.cambiar_estado(id_sol, workflow.ESTADO_PENDIENTE_APROBACION_GERENCIA,
                     m["coordinador"]["id"], "Visto bueno.", firma_b64=FIRMA)
    with pytest.raises(s.TransicionInvalida):
        s.retirar_solicitud(id_sol, m["consultor"]["id"], "Ya no necesito la ausencia.")

    otra = _registrar(m, dias=1)
    s.retirar_solicitud(otra, m["consultor"]["id"], "Ya no necesito la ausencia.")
    with pytest.raises(s.TransicionInvalida):  # ya finalizada: no se retira dos veces
        s.retirar_solicitud(otra, m["consultor"]["id"], "Ya no necesito la ausencia.")


@requiere_bd
def test_la_base_rechaza_un_retiro_que_no_hace_el_dueno(mundo):
    m = mundo
    id_sol = _registrar(m)
    cur = m["cursor"]
    cur.execute("SAVEPOINT ajeno")
    with pytest.raises(Exception, match="solo el consultor dueño"):
        cur.execute(
            """UPDATE solicitud SET estado_workflow = 'Finalizada', resolucion = 'Retirada',
                      motivo_resolucion = 'x', fecha_resolucion = NOW(), id_resuelve = %s
                WHERE id_solicitud = %s""",
            (m["coordinador"]["id"], id_sol),
        )
    cur.execute("ROLLBACK TO SAVEPOINT ajeno")

    cur.execute("SAVEPOINT sin_motivo")
    with pytest.raises(Exception, match="requiere un motivo"):
        cur.execute(
            """UPDATE solicitud SET estado_workflow = 'Finalizada', resolucion = 'Retirada',
                      fecha_resolucion = NOW(), id_resuelve = %s WHERE id_solicitud = %s""",
            (m["consultor"]["id"], id_sol),
        )
    cur.execute("ROLLBACK TO SAVEPOINT sin_motivo")


@requiere_bd
def test_lo_retirado_no_genera_pdf_oficial(mundo, monkeypatch):
    from src.services import documentos

    m, s = mundo, mundo["solicitudes"]
    monkeypatch.setattr(documentos, "obtener_solicitud", s.obtener_solicitud)
    id_sol = _registrar(m)
    s.retirar_solicitud(id_sol, m["consultor"]["id"], "Me equivoqué en las fechas.")
    with pytest.raises(ValueError, match="retirada"):
        documentos.generar_pdf_solicitud(id_sol)


@requiere_bd
def test_los_avisos_llegan_a_quien_debe_actuar(mundo, monkeypatch):
    m = mundo
    monkeypatch.delenv("SETESA_SIN_CORREO", raising=False)
    monkeypatch.setattr(avisos_flujo, "configuracion_smtp", lambda: {"x": 1})
    enviados = []

    def enviar(correo, asunto, cuerpo, config=None):
        enviados.append((correo, asunto, cuerpo))

    id_sol = _registrar(m)

    assert avisos_flujo.avisar(avisos_flujo.NUEVA, id_sol, enviar=enviar) == 1
    assert enviados[-1][0] == m["coordinador"]["correo"]
    assert "pendiente de su visto bueno" in enviados[-1][1]

    enviados.clear()
    avisos_flujo.avisar(avisos_flujo.VISTO_BUENO, id_sol, enviar=enviar)
    assert m["gerencia"]["correo"] in {c for c, _, _ in enviados}
    assert m["coordinador"]["correo"] not in {c for c, _, _ in enviados}

    enviados.clear()
    avisos_flujo.avisar(avisos_flujo.RETIRADA, id_sol, enviar=enviar)
    assert [c for c, _, _ in enviados] == [m["coordinador"]["correo"]]

    enviados.clear()
    avisos_flujo.avisar(avisos_flujo.FINALIZADA, id_sol, enviar=enviar)
    destinos = {c for c, _, _ in enviados}
    assert {m["consultor"]["correo"], m["contabilidad"]["correo"]} <= destinos
    assert m["gerencia"]["correo"] not in destinos


@requiere_bd
def test_un_correo_que_falla_no_impide_avisar_a_los_demas(mundo, monkeypatch):
    m = mundo
    monkeypatch.delenv("SETESA_SIN_CORREO", raising=False)
    monkeypatch.setattr(avisos_flujo, "configuracion_smtp", lambda: {"x": 1})
    id_sol = _registrar(m)
    intentos = []

    def enviar(correo, asunto, cuerpo, config=None):
        intentos.append(correo)
        raise OSError("SMTP caído")

    assert avisos_flujo.avisar(avisos_flujo.FINALIZADA, id_sol, enviar=enviar) == 0
    assert len(intentos) >= 2  # siguió intentando con los demás destinatarios

