# Fase 15: recordatorios por correo para actualizar "Mis datos".

import datetime

import pytest

from src.core import avisos
from src.services import correo

HOY = datetime.date(2026, 10, 11)


def _usuario(actualizado, enviados=()):
    return {
        "id_usuario": 1,
        "nombre_completo": "Ana López",
        "correo_institucional": "ana@example.com",
        "nombre_rol": "Consultor",
        "fecha_actualizacion_datos": actualizado,
        "enviados": set(enviados),
    }


@pytest.mark.parametrize(
    "dias, esperado",
    [(45, None), (31, None), (30, 30), (16, 30), (15, 15), (8, 15),
     (7, 7), (2, 7), (1, 1), (0, 1), (-1, None)],
)
def test_umbral_aplicable(dias, esperado):
    assert avisos.umbral_aplicable(dias) == esperado


def test_planifica_la_etapa_en_curso():
    # Vence el 10/11/2026: hoy faltan 30 días.
    plan = avisos.planificar_avisos([_usuario(datetime.date(2026, 5, 10))], HOY)
    assert len(plan) == 1
    assert plan[0]["umbral"] == 30
    assert plan[0]["fecha_limite"] == datetime.date(2026, 11, 10)


def test_no_repite_una_etapa_ya_enviada():
    usuario = _usuario(datetime.date(2026, 5, 10), enviados={30})
    assert avisos.planificar_avisos([usuario], HOY) == []


def test_si_la_tarea_no_corrio_envia_solo_la_etapa_actual():
    # Faltan 10 días y nunca se envió el de 30: solo corresponde el de 15.
    plan = avisos.planificar_avisos(
        [_usuario(datetime.date(2026, 5, 10))], datetime.date(2026, 10, 31)
    )
    assert [a["umbral"] for a in plan] == [15]


def test_no_avisa_si_falta_mucho():
    assert avisos.planificar_avisos([_usuario(datetime.date(2026, 9, 1))], HOY) == []


def test_redacta_correo_con_fecha_y_pasos():
    aviso = {**_usuario(None), "fecha_limite": datetime.date(2026, 11, 10),
             "dias": 30, "umbral": 30}
    asunto, cuerpo = avisos.redactar(aviso, "https://setesa.example.com")
    assert "10/11/2026" in asunto
    assert "Ana López" in cuerpo
    assert "Mis datos" in cuerpo
    assert "https://setesa.example.com" in cuerpo
    assert "baja" in cuerpo


def test_ultimo_dia_es_urgente():
    aviso = {**_usuario(None), "nombre_rol": "Contabilidad",
             "fecha_limite": datetime.date(2026, 11, 10), "dias": 1, "umbral": 1}
    asunto, cuerpo = avisos.redactar(aviso)
    assert asunto.startswith("URGENTE")
    assert "Contabilidad y RR.HH." in cuerpo


def test_sin_smtp_no_envia(monkeypatch):
    monkeypatch.setattr(avisos, "configuracion_smtp", lambda: None)
    resumen = avisos.enviar_recordatorios()
    assert resumen["enviados"] == 0
    assert "desactivado" in resumen["detalle"][0]


# ---------------------------------------------------------------------------
# Servicio SMTP (con un servidor falso)
# ---------------------------------------------------------------------------
class _SMTPFalso:
    instancias = []

    def __init__(self, host, puerto, timeout=None, **_):
        self.host, self.puerto = host, puerto
        self.acciones = []
        _SMTPFalso.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.acciones.append("starttls")

    def login(self, usuario, password):
        self.acciones.append(("login", usuario))

    def send_message(self, mensaje):
        self.acciones.append(("envio", mensaje["To"], mensaje["Subject"]))


CONFIG = {
    "host": "smtp.example.com",
    "puerto": 587,
    "usuario": "avisos@setesa.example.com",
    "password": "secreto",
    "remitente": "avisos@setesa.example.com",
}


def test_envio_smtp_usa_starttls_y_login(monkeypatch):
    _SMTPFalso.instancias.clear()
    monkeypatch.setattr(correo.smtplib, "SMTP", _SMTPFalso)
    correo.enviar_correo("ana@example.com", "Asunto", "Cuerpo", config=CONFIG)
    acciones = _SMTPFalso.instancias[0].acciones
    assert acciones == [
        "starttls",
        ("login", "avisos@setesa.example.com"),
        ("envio", "ana@example.com", "Asunto"),
    ]


def test_falla_smtp_se_reporta_como_correo_error(monkeypatch):
    class _SMTPCaido(_SMTPFalso):
        def login(self, usuario, password):
            raise correo.smtplib.SMTPAuthenticationError(535, b"bad")

    monkeypatch.setattr(correo.smtplib, "SMTP", _SMTPCaido)
    with pytest.raises(correo.CorreoError):
        correo.enviar_correo("ana@example.com", "Asunto", "Cuerpo", config=CONFIG)


def test_configuracion_incompleta(monkeypatch):
    for nombre in ("SMTP_HOST", "SMTP_USUARIO", "SMTP_PASSWORD"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setattr(correo, "obtener_variable", lambda nombre: None)
    assert correo.configuracion_smtp() is None
    assert not correo.correo_configurado()
