# Prueba del flujo completo de SETESA Workflow, de punta a punta.
#
# Recorre con los cinco roles (IT, Consultor, Coordinador GTC, Gerencia y
# Contabilidad y RR.HH.) todo lo que hace el sistema, contra la base de PRUEBAS:
# altas, acceso, «Mis datos», catálogo, solicitudes aprobadas y denegadas,
# evidencias, reasignación, PDF final, avisos, vigencia, indicadores y las
# pantallas de cada rol.
#
# - Los pasos se ejecutan EN ORDEN y comparten el mismo "mundo" de datos.
# - Los datos son temporales (prefijo PYTEST_FLUJO) y se borran al terminar.
# - El repositorio de archivos es una carpeta temporal (no toca el bucket real)
#   y el correo se simula (no se envía nada).
# - Las firmas se envían como imagen generada: el recuadro de dibujo de la
#   pantalla es un componente del navegador (ver docs/PRUEBA_MANUAL.md).
# - Se omite si no hay DATABASE_URL.

import base64
import datetime
import io
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

from src.core import (
    auth,
    avisos,
    evidencias,
    indicadores,
    intentos,
    motivos,
    notificaciones,
    perfil,
    reasignacion,
    recordatorios,
    sesion,
    solicitudes,
    vigencia,
)
from src.core.database import get_connection
from src.core.gestion_usuarios import (
    CorreoDuplicado,
    DatosInvalidos,
    OperacionNoPermitida,
    cambiar_estado_usuario,
    crear_usuario,
    desbloquear_acceso,
    listar_usuarios,
)
from src.core.utils import calcular_dias_habiles
from src.core.validaciones import ValidacionError
from src.core.vacaciones import obtener_saldo_vacaciones
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)
from src.features import coordinador as panel_coordinador
from src.features import dashboard
from src.features.registro import obtener_mis_solicitudes
from src.services import almacenamiento, documentos

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)

RUTA_APP = Path(__file__).resolve().parents[1] / "app.py"
CLAVE = "ClaveFlujo2026"
MOTIVO_NUEVO = "PERMISO POR ESTUDIO FLUJO"
PDF_EVIDENCIA = b"%PDF-1.4\n% constancia del IGSS\n%%EOF\n"


def _firma():
    # Como las del recuadro de la app (utils_firma): fondo blanco, 3:1.
    imagen = Image.new("RGB", (300, 100), (255, 255, 255))
    ImageDraw.Draw(imagen).line([(20, 70), (80, 30), (140, 75), (200, 25), (280, 60)],
                                fill=(0, 0, 0), width=4)
    b = io.BytesIO()
    imagen.save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def _dias(inicio, fin):
    return calcular_dias_habiles(inicio, fin, set())


def _texto_pdf(contenido):
    import pymupdf

    with pymupdf.open(stream=contenido, filetype="pdf") as doc:
        return " ".join(pagina.get_text() for pagina in doc)


def _sql(sentencia, params=None, borrado=False, devolver=False):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                if borrado:
                    cursor.execute("SET LOCAL setesa.permitir_borrado = 'on'")
                cursor.execute(sentencia, params)
                return cursor.fetchall() if devolver else cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Mundo de datos temporal
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def mundo(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(almacenamiento, "REPOSITORIO_DIR", tmp_path_factory.mktemp("repo"))
    mp.setattr(almacenamiento, "configuracion_supabase", lambda: None)

    filas = _sql(
        "SELECT u.id_usuario FROM usuario u JOIN rol r USING (id_rol) "
        "WHERE r.nombre_rol = 'IT' AND u.estado_vigencia ORDER BY 1 LIMIT 1",
        devolver=True,
    )
    if not filas:
        pytest.skip("Hace falta un usuario IT vigente en la base de pruebas.")

    marca = uuid4().hex[:6]
    m = {"it": filas[0][0], "marca": marca, "ids": [], "log_vigencia": [],
         "solicitudes": {}, "usuarios": {}}
    yield m

    # --- Limpieza: todo lo creado por la prueba ---
    ids = list(m["ids"])
    correos = [d["correo"] for d in m["usuarios"].values()]
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("SET LOCAL setesa.permitir_borrado = 'on'")
                if ids:
                    cursor.execute("DELETE FROM solicitud WHERE id_usuario = ANY(%s)", (ids,))
                cursor.execute("DELETE FROM motivo_ausencia WHERE nombre = %s", (MOTIVO_NUEVO,))
                cursor.execute("DELETE FROM intento_login WHERE correo = ANY(%s)", (correos,))
                if m["log_vigencia"]:
                    cursor.execute("DELETE FROM vigencia_log WHERE id_log = ANY(%s)",
                                   (m["log_vigencia"],))
                if ids:
                    cursor.execute(
                        "DELETE FROM usuario_log WHERE id_afectado = ANY(%s) OR id_ejecutor = ANY(%s)",
                        (ids, ids))
                    cursor.execute("DELETE FROM usuario WHERE id_usuario = ANY(%s)", (ids,))
    finally:
        conn.close()
    mp.undo()


def _u(m, clave):
    return m["usuarios"][clave]["id"]


# ===========================================================================
# 1. Alta de usuarios (IT)
# ===========================================================================
def test_01_it_crea_los_usuarios_de_cada_rol(mundo):
    m = mundo
    plan = {
        "consultor": ("Consultor", "Consultor"),
        "consultor2": ("Consultor", "Consultor"),
        "coord_a": ("Coordinador GTC", "Coordinador GTC"),
        "coord_b": ("Coordinador GTC", "Coordinador GTC"),
        "gerencia": ("Administrador", "Gerente General"),
        "conta": ("Contabilidad", "Contabilidad y RR.HH."),
    }
    for clave, (rol, etiqueta) in plan.items():
        correo = f"pytest_flujo_{clave}_{m['marca']}@example.com"
        id_usuario = crear_usuario(m["it"], f"PYTEST_FLUJO {etiqueta} {clave}", correo, rol, CLAVE, 15)
        id_usuario = id_usuario if isinstance(id_usuario, int) else next(
            f[0] for f in _sql("SELECT id_usuario FROM usuario WHERE correo_institucional = %s",
                               (correo,), devolver=True))
        m["ids"].append(id_usuario)
        m["usuarios"][clave] = {"id": id_usuario, "correo": correo, "rol": rol}

    df = listar_usuarios()
    for datos in m["usuarios"].values():
        assert datos["id"] in df["id_usuario"].tolist()


def test_02_it_valida_duplicados_claves_debiles_y_permisos(mundo):
    m = mundo
    con = m["usuarios"]["consultor"]
    with pytest.raises(CorreoDuplicado):
        crear_usuario(m["it"], "Otro", con["correo"], "Consultor", CLAVE)
    with pytest.raises(DatosInvalidos):
        crear_usuario(m["it"], "Débil", f"debil_{m['marca']}@example.com", "Consultor", "corta")
    with pytest.raises(OperacionNoPermitida):  # un consultor no gestiona usuarios
        crear_usuario(con["id"], "Intruso", f"intruso_{m['marca']}@example.com", "IT", CLAVE)


# ===========================================================================
# 2. Acceso y seguridad
# ===========================================================================
def test_03_cada_rol_inicia_sesion_y_la_clave_incorrecta_falla(mundo):
    for clave, datos in mundo["usuarios"].items():
        resultado = auth.login_user(datos["correo"], CLAVE)
        assert resultado is not None, clave
        assert resultado[3] == datos["rol"] and resultado[2] is True
    assert auth.login_user(mundo["usuarios"]["consultor"]["correo"], "incorrecta") is None


def test_04_cinco_fallos_bloquean_y_it_desbloquea(mundo):
    m = mundo
    correo = m["usuarios"]["consultor2"]["correo"]
    for _ in range(intentos.MAX_INTENTOS):
        assert auth.login_user(correo, "mala") is None
    with pytest.raises(intentos.CuentaBloqueada):
        auth.login_user(correo, CLAVE)  # ni la clave correcta sirve
    desbloquear_acceso(m["it"], correo)
    assert auth.login_user(correo, CLAVE) is not None


def test_05_la_sesion_expira_por_inactividad_y_duracion():
    ahora = datetime.datetime(2026, 11, 5, 10, 0)
    estado = {}
    assert sesion.motivo_expiracion(estado, ahora) is None
    assert sesion.motivo_expiracion(estado, ahora + datetime.timedelta(minutes=31)) == sesion.MOTIVO_INACTIVIDAD
    sesion.registrar_interaccion(estado, ahora + datetime.timedelta(hours=8))
    assert sesion.motivo_expiracion(estado, ahora + datetime.timedelta(hours=8, minutes=1)) == sesion.MOTIVO_DURACION


# ===========================================================================
# 3. «Mis datos»
# ===========================================================================
def test_06_consultor_y_contabilidad_actualizan_sus_datos(mundo):
    m = mundo
    consultor, conta = _u(m, "consultor"), _u(m, "conta")
    limite = perfil.actualizar_mis_datos(consultor, "Consultor Técnico", "C-0147", "5555-1234")
    assert limite > datetime.date.today()
    datos = perfil.obtener_perfil(consultor)
    assert (datos["puesto"], datos["codigo_empleado"], datos["telefono"]) == (
        "Consultor Técnico", "C-0147", "55551234")
    crudo = _sql("SELECT telefono FROM usuario WHERE id_usuario = %s", (consultor,), devolver=True)[0][0]
    assert crudo.startswith("fernet:")  # el teléfono se guarda cifrado

    perfil.actualizar_mis_datos(conta, "Contadora", None, "5555-9999")
    assert perfil.obtener_perfil(conta)["codigo_empleado"] == ""
    for rol in ("coord_a", "gerencia"):  # excluidos de la actualización
        with pytest.raises(perfil.PerfilError):
            perfil.actualizar_mis_datos(_u(m, rol), "X", "C-1", "55551234")


# ===========================================================================
# 4. Catálogo de motivos (Gerencia)
# ===========================================================================
def test_07_gerencia_mantiene_el_catalogo(mundo):
    m = mundo
    assert motivos.crear_motivo(_u(m, "gerencia"), MOTIVO_NUEVO.lower()) == MOTIVO_NUEVO
    assert MOTIVO_NUEVO in motivos.opciones_activas()
    with pytest.raises(motivos.MotivoError):
        motivos.crear_motivo(_u(m, "consultor"), "NO AUTORIZADO")

    id_duelo = int(_sql("SELECT id_motivo FROM motivo_ausencia WHERE nombre = 'DUELO'", devolver=True)[0][0])
    motivos.cambiar_estado_motivo(_u(m, "gerencia"), id_duelo, False)
    assert "DUELO" not in motivos.opciones_activas()
    with pytest.raises(Exception, match="catálogo"):  # la base lo rechaza
        solicitudes.registrar_solicitud(
            _u(m, "consultor"), "DUELO", datetime.date(2037, 1, 5), datetime.date(2037, 1, 5),
            _u(m, "coord_a"), "Consultor", "C-1", 1, "x", None)
    motivos.cambiar_estado_motivo(_u(m, "gerencia"), id_duelo, True)
    with pytest.raises(motivos.MotivoError, match="regla propia"):
        id_vac = int(_sql("SELECT id_motivo FROM motivo_ausencia WHERE nombre='VACACION'", devolver=True)[0][0])
        motivos.cambiar_estado_motivo(_u(m, "gerencia"), id_vac, False)


# ===========================================================================
# 5. Vacaciones: registro, bandeja del banco, aprobación de Gerencia y PDF
# ===========================================================================
def _registrar(m, tipo, inicio, fin, coord="coord_a", explicacion="Solicitud de prueba del flujo.",
               archivos=None, quien="consultor"):
    ev = evidencias.subir_evidencias(archivos or [])
    return solicitudes.registrar_solicitud(
        _u(m, quien), tipo, inicio, fin, _u(m, coord), "Consultor Técnico", "C-0147",
        _dias(inicio, fin), explicacion, _firma(), evidencias=ev)


def test_08_consultor_registra_vacaciones_y_se_descuenta_el_saldo(mundo):
    m = mundo
    antes = obtener_saldo_vacaciones(_u(m, "consultor"), anio=2037)["disponibles"]
    inicio, fin = datetime.date(2037, 3, 2), datetime.date(2037, 3, 4)  # lunes a miércoles
    id_sol = _registrar(m, "VACACION", inicio, fin, explicacion="Vacaciones familiares.")
    m["solicitudes"]["aprobada"] = id_sol

    assert obtener_saldo_vacaciones(_u(m, "consultor"), anio=2037)["disponibles"] == antes - 3
    assert solicitudes.obtener_estado(id_sol) == ESTADO_PENDIENTE_FIRMA_COORDINADOR
    historial = obtener_mis_solicitudes(_u(m, "consultor"))
    assert id_sol in historial["id_solicitud"].tolist()
    assert "Vacaciones familiares." in historial.loc[historial["id_solicitud"] == id_sol, "explicacion"].iloc[0]


def test_09_la_bandeja_es_solo_del_coordinador_asignado(mundo):
    m, id_sol = mundo, mundo["solicitudes"]["aprobada"]
    assert id_sol in panel_coordinador.obtener_solicitudes_pendientes(_u(m, "coord_a"))["id_solicitud"].tolist()
    assert id_sol not in panel_coordinador.obtener_solicitudes_pendientes(_u(m, "coord_b"))["id_solicitud"].tolist()
    with pytest.raises(solicitudes.CoordinadorNoAsignado):
        solicitudes.cambiar_estado(id_sol, ESTADO_PENDIENTE_APROBACION_GERENCIA,
                                   _u(m, "coord_b"), firma_b64=_firma())


def test_10_recordatorio_al_banco_con_enlace_de_correo(mundo):
    m, id_sol = mundo, mundo["solicitudes"]["aprobada"]
    envio = recordatorios.registrar_recordatorio(id_sol, _u(m, "consultor"))
    assert envio["id_destinatario"] == _u(m, "coord_a")
    assert len(recordatorios.obtener_recordatorios_pendientes(_u(m, "coord_a"))) == 1
    with pytest.raises(recordatorios.RecordatorioReciente):  # no más de uno por día
        recordatorios.registrar_recordatorio(id_sol, _u(m, "consultor"))
    assert recordatorios.construir_enlace_correo(envio["correo"], "Asunto", "Cuerpo").startswith("mailto:")


def test_11_el_banco_da_el_visto_bueno_y_gerencia_aprueba(mundo):
    m, id_sol = mundo, mundo["solicitudes"]["aprobada"]
    solicitudes.cambiar_estado(id_sol, ESTADO_PENDIENTE_APROBACION_GERENCIA,
                               _u(m, "coord_a"), "Visto bueno.", firma_b64=_firma())
    assert recordatorios.obtener_recordatorios_pendientes(_u(m, "coord_a")).empty  # atendidos
    with pytest.raises(solicitudes.TransicionInvalida):  # no se puede saltar etapas
        solicitudes.cambiar_estado(id_sol, ESTADO_PENDIENTE_FIRMA_COORDINADOR, _u(m, "gerencia"))
    solicitudes.cambiar_estado(id_sol, ESTADO_FINALIZADA, _u(m, "gerencia"),
                               "Aprobada.", firma_b64=_firma())
    datos = solicitudes.obtener_solicitud(id_sol)
    assert (datos["estado_workflow"], datos["resolucion"]) == (ESTADO_FINALIZADA, "Aprobada")
    assert len(solicitudes.obtener_historial(id_sol)) == 4


def test_12_al_finalizar_se_avisa_a_contabilidad_y_al_consultor(mundo):
    m, id_sol = mundo, mundo["solicitudes"]["aprobada"]
    for quien in ("conta", "consultor"):
        df = notificaciones.listar_notificaciones(_u(m, quien))
        assert id_sol in df["id_solicitud"].tolist(), quien
        assert "APROBADA" in df.loc[df["id_solicitud"] == id_sol, "mensaje"].iloc[0]
    assert id_sol not in notificaciones.listar_notificaciones(_u(m, "coord_a"))["id_solicitud"].tolist()
    assert notificaciones.contar_no_leidas(_u(m, "conta")) >= 1
    notificaciones.marcar_leidas(_u(m, "conta"))
    assert notificaciones.contar_no_leidas(_u(m, "conta")) == 0


def test_13_pdf_final_inmutable_con_sello_estable(mundo):
    id_sol = mundo["solicitudes"]["aprobada"]
    clave = documentos.generar_pdf_solicitud(id_sol)
    datos = solicitudes.obtener_solicitud(id_sol)
    assert datos["pdf_inmutable"] and clave.startswith(f"pdf/{id_sol}/final_")

    nombre, contenido = documentos.preparar_pdf_descarga(id_sol, regenerar=True)
    assert nombre.endswith("_final.pdf") and contenido.startswith(b"%PDF")
    assert contenido.count(b"/Subtype /Image") == 4  # logo + tres firmas
    assert solicitudes.obtener_solicitud(id_sol)["pdf_hash"] == datos["pdf_hash"]  # sello estable
    assert documentos.verificar_integridad_pdf(id_sol)["estado"] == "ok"

    texto = _texto_pdf(contenido)
    for esperado in ("ACCION DE PERSONAL", "RESOLUCION: APROBADA", "02/03/2037", "04/03/2037", "Vacaciones familiares."):
        assert esperado in texto, esperado

    # Alterar el archivo en el repositorio se detecta.
    ruta = almacenamiento.REPOSITORIO_DIR / clave
    original = ruta.read_bytes()
    ruta.write_bytes(original + b"\n% alterado\n")
    assert documentos.verificar_integridad_pdf(id_sol)["estado"] == "alterado"
    ruta.write_bytes(original)


def test_14_un_expediente_finalizado_es_inalterable(mundo):
    id_sol = mundo["solicitudes"]["aprobada"]
    with pytest.raises(Exception, match="SETESA"):
        _sql("UPDATE solicitud SET explicacion = 'cambiada' WHERE id_solicitud = %s", (id_sol,))
    with pytest.raises(Exception, match="SETESA"):
        _sql("DELETE FROM solicitud WHERE id_solicitud = %s", (id_sol,))
    with pytest.raises(Exception, match="SETESA"):
        _sql("UPDATE solicitud_historial SET observacion = 'x' WHERE id_solicitud = %s", (id_sol,))


# ===========================================================================
# 6. Denegaciones y devolución de días
# ===========================================================================
def test_15_el_banco_deniega_y_los_dias_vuelven_al_saldo(mundo):
    m = mundo
    antes = obtener_saldo_vacaciones(_u(m, "consultor"), anio=2037)["disponibles"]
    id_sol = _registrar(m, "VACACION", datetime.date(2037, 5, 4), datetime.date(2037, 5, 5))
    m["solicitudes"]["denegada_banco"] = id_sol
    assert obtener_saldo_vacaciones(_u(m, "consultor"), anio=2037)["disponibles"] == antes - 2

    with pytest.raises(solicitudes.MotivoRequerido):
        solicitudes.denegar_solicitud(id_sol, _u(m, "coord_a"), "corto", _firma())
    with pytest.raises(solicitudes.CoordinadorNoAsignado):
        solicitudes.denegar_solicitud(id_sol, _u(m, "coord_b"), "El banco necesita al consultor.", _firma())
    solicitudes.denegar_solicitud(id_sol, _u(m, "coord_a"),
                                  "El banco necesita al consultor en el proyecto urgente.", _firma())

    datos = solicitudes.obtener_solicitud(id_sol)
    assert (datos["estado_workflow"], datos["resolucion"]) == (ESTADO_FINALIZADA, "Denegada")
    assert datos["motivo_resolucion"].startswith("El banco necesita")
    assert obtener_saldo_vacaciones(_u(m, "consultor"), anio=2037)["disponibles"] == antes  # devuelto

    documentos.generar_pdf_solicitud(id_sol)
    texto = _texto_pdf(documentos.preparar_pdf_descarga(id_sol)[1])
    assert "RESOLUCION: DENEGADA POR COORDINADOR GTC" in texto and "proyecto urgente" in texto
    df = notificaciones.listar_notificaciones(_u(m, "conta"))
    assert "DENEGADA" in df.loc[df["id_solicitud"] == id_sol, "mensaje"].iloc[0]
    # El aviso no revela el motivo de la denegación.
    assert "proyecto urgente" not in df.loc[df["id_solicitud"] == id_sol, "mensaje"].iloc[0]


def test_16_gerencia_deniega_en_su_etapa(mundo):
    m = mundo
    id_sol = _registrar(m, "PERMISO SIN GOCE DE SUELDO", datetime.date(2037, 6, 1), datetime.date(2037, 6, 2))
    m["solicitudes"]["denegada_gerencia"] = id_sol
    solicitudes.cambiar_estado(id_sol, ESTADO_PENDIENTE_APROBACION_GERENCIA,
                               _u(m, "coord_a"), firma_b64=_firma())
    with pytest.raises(solicitudes.NoAutorizadoParaDenegar):  # el banco ya no puede
        solicitudes.denegar_solicitud(id_sol, _u(m, "coord_a"), "Motivo suficiente largo.", _firma())
    solicitudes.denegar_solicitud(id_sol, _u(m, "gerencia"), "No hay presupuesto para este permiso.", _firma())
    documentos.generar_pdf_solicitud(id_sol)
    texto = _texto_pdf(documentos.preparar_pdf_descarga(id_sol)[1])
    assert "RESOLUCION: DENEGADA POR GERENCIA" in texto and "No hay presupuesto" in texto


# ===========================================================================
# 7. Evidencias
# ===========================================================================
def test_17_la_suspension_igss_exige_constancia_y_se_controla_el_acceso(mundo):
    m = mundo
    inicio, fin = datetime.date(2037, 7, 6), datetime.date(2037, 7, 8)
    with pytest.raises(ValidacionError, match="IGSS"):
        _registrar(m, "SUSPENSIÓN IGSS", inicio, fin)
    with pytest.raises(evidencias.EvidenciaError):
        _registrar(m, "SUSPENSIÓN IGSS", inicio, fin, archivos=[("virus.exe", b"MZ")])

    id_sol = _registrar(m, "SUSPENSIÓN IGSS", inicio, fin, archivos=[("constancia.pdf", PDF_EVIDENCIA)])
    m["solicitudes"]["igss"] = id_sol

    for quien in ("consultor", "conta", "gerencia"):
        df = evidencias.listar_evidencias(id_sol, _u(m, quien))
        assert len(df) == 1, quien
    for quien in ("coord_a", "consultor2"):  # el banco y otros consultores no la ven
        with pytest.raises(evidencias.EvidenciaError):
            evidencias.listar_evidencias(id_sol, _u(m, quien))

    id_ev = int(evidencias.listar_evidencias(id_sol, _u(m, "conta"))["id_evidencia"].iloc[0])
    nombre, tipo, contenido = evidencias.descargar_evidencia(id_ev, _u(m, "gerencia"))
    assert (nombre, tipo, contenido) == ("constancia.pdf", "application/pdf", PDF_EVIDENCIA)
    with pytest.raises(evidencias.EvidenciaError):
        evidencias.descargar_evidencia(id_ev, _u(m, "coord_a"))

    assert evidencias.agregar_evidencias(id_sol, _u(m, "consultor"), [("foto.png", _png())]) == 1


def _png():
    b = io.BytesIO()
    Image.new("RGB", (4, 4), (0, 0, 255)).save(b, "PNG")
    return b.getvalue()


def test_18_un_motivo_nuevo_sale_como_otros_en_el_pdf(mundo):
    m = mundo
    id_sol = _registrar(m, MOTIVO_NUEVO, datetime.date(2037, 8, 3), datetime.date(2037, 8, 4))
    m["solicitudes"]["nuevo"] = id_sol
    documentos.generar_pdf_solicitud(id_sol)
    texto = _texto_pdf(documentos.preparar_pdf_descarga(id_sol)[1])
    assert f"({MOTIVO_NUEVO})" in texto


# ===========================================================================
# 8. Reasignación de coordinador
# ===========================================================================
def test_19_al_salir_un_coordinador_sus_expedientes_pasan_a_otro(mundo):
    m = mundo
    id_sol = _registrar(m, "PERMISO CON GOCE DE SUELDO", datetime.date(2037, 9, 1), datetime.date(2037, 9, 1))
    m["solicitudes"]["reasignada"] = id_sol

    cambiar_estado_usuario(m["it"], _u(m, "coord_a"), False)  # IT da de baja al coordinador
    assert reasignacion.contar_pendientes_coordinador(_u(m, "coord_a")) >= 2  # igss, nuevo, reasignada...
    huerfanos = reasignacion.listar_expedientes_reasignables()
    assert not huerfanos.loc[huerfanos["id_solicitud"] == id_sol, "coordinador_vigente"].iloc[0]

    with pytest.raises(reasignacion.ReasignacionError):
        reasignacion.reasignar_coordinador(id_sol, _u(m, "coord_b"), m["it"], " ")  # exige motivo
    for clave in ("reasignada", "igss", "nuevo"):
        reasignacion.reasignar_coordinador(m["solicitudes"][clave], _u(m, "coord_b"),
                                           _u(m, "gerencia"), "El coordinador salió del banco.")
    assert id_sol in panel_coordinador.obtener_solicitudes_pendientes(_u(m, "coord_b"))["id_solicitud"].tolist()
    with pytest.raises(solicitudes.CoordinadorNoAsignado):
        solicitudes.cambiar_estado(id_sol, ESTADO_PENDIENTE_APROBACION_GERENCIA,
                                   _u(m, "coord_a"), firma_b64=_firma())
    solicitudes.cambiar_estado(id_sol, ESTADO_PENDIENTE_APROBACION_GERENCIA,
                               _u(m, "coord_b"), firma_b64=_firma())
    assert "Reasignada" in " ".join(solicitudes.obtener_historial(id_sol)["observacion"].dropna())


# ===========================================================================
# 9. Vigencia y avisos por correo
# ===========================================================================
def test_20_quien_no_actualiza_sus_datos_pasa_a_baja_y_se_puede_reactivar(mundo):
    m = mundo
    id_c2 = _u(m, "consultor2")
    _sql("UPDATE usuario SET fecha_actualizacion_datos = NOW() - INTERVAL '7 months' WHERE id_usuario = %s", (id_c2,))
    assert id_c2 in vigencia.obtener_inactivos()["id_usuario"].tolist()

    afectados, id_log = vigencia.ejecutar_depuracion(id_ejecutor=_u(m, "gerencia"))
    m["log_vigencia"].append(id_log)
    assert id_c2 in afectados["id_usuario"].tolist()
    assert vigencia.usuario_activo(id_c2) is False
    assert auth.login_user(m["usuarios"]["consultor2"]["correo"], CLAVE)[2] is False  # acceso denegado

    m["log_vigencia"].append(vigencia.reactivar_usuario(id_c2, id_ejecutor=_u(m, "gerencia")))
    assert vigencia.usuario_activo(id_c2) is True
    assert perfil.dias_restantes(perfil.obtener_perfil(id_c2)["fecha_actualizacion_datos"]) > 170  # plazo reiniciado

    # Coordinador, Gerencia e IT no vencen automáticamente.
    _sql("UPDATE usuario SET fecha_actualizacion_datos = NOW() - INTERVAL '8 months' WHERE id_usuario = %s",
         (_u(m, "gerencia"),))
    afectados, id_log = vigencia.ejecutar_depuracion(id_ejecutor=m["it"])
    m["log_vigencia"].append(id_log)
    assert _u(m, "gerencia") not in afectados["id_usuario"].tolist()


def test_21_el_recordatorio_por_correo_sale_una_vez_por_etapa(mundo, monkeypatch):
    m = mundo
    id_c = _u(m, "consultor")
    _sql("UPDATE usuario SET fecha_actualizacion_datos = NOW() - INTERVAL '6 months' + INTERVAL '20 days' "
         "WHERE id_usuario = %s", (id_c,))
    enviados = []
    monkeypatch.setattr(avisos, "configuracion_smtp", lambda: {"simulado": True})

    def falso(destino, asunto, cuerpo, config=None):
        enviados.append((destino, asunto, cuerpo))

    avisos.enviar_recordatorios(enviar=falso)
    propios = [e for e in enviados if e[0] == m["usuarios"]["consultor"]["correo"]]
    assert len(propios) == 1 and "Mis datos" in propios[0][2]

    enviados.clear()
    avisos.enviar_recordatorios(enviar=falso)  # la misma etapa no se repite
    assert not [e for e in enviados if e[0] == m["usuarios"]["consultor"]["correo"]]
    _sql("UPDATE usuario SET fecha_actualizacion_datos = NOW() WHERE id_usuario = %s", (id_c,))


# ===========================================================================
# 10. Dashboard e indicadores
# ===========================================================================
def test_22_el_dashboard_refleja_los_expedientes_y_los_indicadores(mundo):
    m = mundo
    df = dashboard.obtener_solicitudes()
    propios = df[df["id_solicitud"].isin(m["solicitudes"].values())]
    assert len(propios) == len(m["solicitudes"])
    assert {"Aprobada", "Denegada"} <= set(propios["resolucion"].dropna())

    tiempos = indicadores.calcular_tiempos(indicadores.obtener_tiempos_resolucion())
    assert tiempos["resueltas"] >= 3 and tiempos["total"] is not None
    assert tiempos["aprobadas"] is not None and tiempos["denegadas"] is not None

    resumen = indicadores.resumen_usuarios(indicadores.obtener_usuarios())
    assert resumen["total"] >= 6 and resumen["vigentes"] >= 6 - 1
    assert 0 <= resumen["pct_inactivos"] <= 100


# ===========================================================================
# 11. Pantallas de cada rol y servidor
# ===========================================================================
def _sesion(m, clave):
    at = AppTest.from_file(str(RUTA_APP), default_timeout=90)
    datos = m["usuarios"][clave]
    at.session_state["logged_in"] = True
    at.session_state["id_usuario"] = datos["id"]
    at.session_state["nombre"] = f"PYTEST_FLUJO {clave}"
    at.session_state["rol"] = datos["rol"]
    return at.run()


@pytest.mark.parametrize(
    "clave, texto",
    [
        ("consultor", "Panel Operativo"),
        ("coord_b", "Portal de Aprobaciones"),
        ("gerencia", "Panel Gerencial"),
        ("conta", "Contabilidad y RR.HH."),
    ],
)
def test_23_las_pantallas_de_cada_rol_cargan_sin_errores(mundo, clave, texto):
    at = _sesion(mundo, clave)
    assert not at.exception, [e.value for e in at.exception]
    visible = " ".join(x.value for x in [*at.markdown, *at.title, *at.header])
    assert texto in visible


def test_24_pantalla_de_it_y_sus_pestanas(mundo):
    at = AppTest.from_file(str(RUTA_APP), default_timeout=90)
    at.session_state["logged_in"] = True
    at.session_state["id_usuario"] = mundo["it"]
    at.session_state["nombre"] = "IT"
    at.session_state["rol"] = "IT"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 5  # usuarios, crear, reasignar, por vencer, auditoría


def test_25_gerencia_tiene_las_cinco_pestanas_y_ve_la_gestion(mundo):
    at = _sesion(mundo, "gerencia")
    assert len(at.tabs) == 5
    assert any("Gestión de Workflow" in x.value for x in at.markdown)


def test_26_el_inicio_de_sesion_por_formulario_funciona(mundo):
    at = AppTest.from_file(str(RUTA_APP), default_timeout=90).run()
    at.text_input[0].set_value(mundo["usuarios"]["consultor"]["correo"])
    at.text_input[1].set_value("incorrecta")
    at.button[0].click().run()
    assert any("Credenciales incorrectas" in e.value for e in at.error)
    at.text_input[1].set_value(CLAVE)
    at.button[0].click().run()
    assert at.session_state["logged_in"] is True and at.session_state["rol"] == "Consultor"
    assert not at.exception


def test_27_el_servidor_de_streamlit_arranca_y_responde(mundo):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    proceso = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(RUTA_APP), "--server.headless", "true",
         "--server.port", str(puerto), "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(RUTA_APP.parent))
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/_stcore/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except OSError:
                time.sleep(1)
        pytest.fail("El servidor de Streamlit no respondió en 60 segundos.")
    finally:
        proceso.terminate()
        try:
            proceso.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proceso.kill()
