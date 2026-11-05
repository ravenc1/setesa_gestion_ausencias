# Fase 24: ajustes de las pruebas manuales (rendimiento, filtros, soporte y
# cambio de contraseña).

import datetime
import os
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest

from src.core import cache, cuenta, database, intentos
from src.core.reportes import filtrar_solicitudes
from src.features import dashboard
from src.ui import estilos
from src.ui.pestanas import abierta

requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)


# ---------------------------------------------------------------------------
# Reserva de conexiones
# ---------------------------------------------------------------------------
class _ConexionFalsa:
    def __init__(self, cerrada=False):
        self.closed = 1 if cerrada else 0
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = 1


class _ReservaFalsa:
    def __init__(self):
        self.devueltas = []

    def putconn(self, conexion, close=False):
        self.devueltas.append((conexion, close))


def test_close_devuelve_la_conexion_a_la_reserva_sin_cerrarla():
    reserva, real = _ReservaFalsa(), _ConexionFalsa()
    envuelta = database.ConexionDeReserva(reserva, real)
    envuelta.close()
    envuelta.close()  # idempotente
    assert reserva.devueltas == [(real, False)]
    assert real.rollbacks == 1  # nunca vuelve con una transacción abierta
    assert real.closed == 0


def test_una_conexion_cerrada_se_descarta_al_devolverla():
    reserva, real = _ReservaFalsa(), _ConexionFalsa(cerrada=True)
    database.ConexionDeReserva(reserva, real).close()
    assert reserva.devueltas == [(real, True)]


def test_la_conexion_de_emergencia_si_se_cierra():
    real = _ConexionFalsa()
    database.ConexionDeReserva(None, real).close()
    assert real.closed == 1


def test_los_atributos_pasan_a_la_conexion_real():
    real = _ConexionFalsa()
    envuelta = database.ConexionDeReserva(_ReservaFalsa(), real)
    envuelta.autocommit = True
    assert real.autocommit is True
    assert envuelta.closed == 0


def test_una_conexion_inactiva_mucho_tiempo_se_revalida(monkeypatch):
    class _Cursor:
        def __init__(self, falla):
            self.falla = falla

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

        def execute(self, q):
            if self.falla:
                raise RuntimeError("conexión cerrada por el servidor")

    class _Conexion(_ConexionFalsa):
        def __init__(self, falla):
            super().__init__()
            self.falla = falla

        def cursor(self):
            return _Cursor(self.falla)

    reciente, vieja_viva, vieja_muerta = _Conexion(False), _Conexion(False), _Conexion(True)
    ahora = 10_000.0
    monkeypatch.setattr(database.time, "monotonic", lambda: ahora)
    database._ultimo_uso.clear()
    database._ultimo_uso[id(reciente)] = ahora - 2          # no se revalida
    database._ultimo_uso[id(vieja_viva)] = ahora - 600       # SELECT 1 correcto
    database._ultimo_uso[id(vieja_muerta)] = ahora - 600     # el servidor la cerró
    assert database._conexion_valida(reciente)
    assert database._conexion_valida(vieja_viva)
    assert not database._conexion_valida(vieja_muerta)


# ---------------------------------------------------------------------------
# Guardado temporal de lecturas
# ---------------------------------------------------------------------------
def test_la_lectura_se_guarda_y_una_escritura_la_invalida(monkeypatch):
    monkeypatch.delenv("SETESA_SIN_CACHE", raising=False)
    llamadas = []

    @cache.lectura(ttl=60)
    def leer(x):
        llamadas.append(x)
        return x * 2

    @cache.escritura
    def escribir():
        return "ok"

    cache.invalidar()
    assert (leer(2), leer(2)) == (4, 4)
    assert llamadas == [2]                  # la segunda salió de la copia
    assert escribir() == "ok"
    assert leer(2) == 4 and llamadas == [2, 2]  # tras escribir, se lee de nuevo
    cache.invalidar()


def test_una_escritura_que_falla_tambien_invalida(monkeypatch):
    monkeypatch.delenv("SETESA_SIN_CACHE", raising=False)
    llamadas = []

    @cache.lectura(ttl=60)
    def leer():
        llamadas.append(1)
        return 1

    @cache.escritura
    def falla():
        raise RuntimeError("fallo a medias")

    cache.invalidar()
    leer()
    with pytest.raises(RuntimeError):
        falla()
    leer()
    assert len(llamadas) == 2
    cache.invalidar()


def test_con_el_interruptor_no_se_guarda_nada(monkeypatch):
    monkeypatch.setenv("SETESA_SIN_CACHE", "1")
    llamadas = []

    @cache.lectura(ttl=60)
    def leer():
        llamadas.append(1)

    leer()
    leer()
    assert len(llamadas) == 2


def test_las_validaciones_de_negocio_no_usan_el_guardado():
    from src.core import vacaciones, validaciones

    assert hasattr(vacaciones, "calcular_saldo_vacaciones")
    assert validaciones.calcular_saldo_vacaciones is vacaciones.calcular_saldo_vacaciones


# ---------------------------------------------------------------------------
# Pestañas perezosas y filtros
# ---------------------------------------------------------------------------
def test_pestana_abierta():
    assert abierta(SimpleNamespace(open=True))
    assert not abierta(SimpleNamespace(open=False))
    assert abierta(SimpleNamespace())  # sin información: se muestra


def test_filtrar_por_id_de_usuario_no_confunde_nombres_parecidos():
    df = pd.DataFrame({
        "id_usuario": [1, 2],
        "nombre_completo": ["Ana", "Ana María"],
        "estado_workflow": ["Finalizada"] * 2,
        "tipo_ausencia": ["VACACION"] * 2,
        "fecha_inicio": pd.to_datetime(["2026-12-01"] * 2),
        "fecha_fin": pd.to_datetime(["2026-12-02"] * 2),
    })
    assert len(filtrar_solicitudes(df, nombre="Ana")) == 2   # coincidencia parcial
    assert filtrar_solicitudes(df, id_usuario=1)["id_usuario"].tolist() == [1]


def test_selector_de_colaboradores_marca_a_los_inactivos(monkeypatch):
    monkeypatch.setattr(dashboard, "listar_colaboradores", lambda: pd.DataFrame({
        "id_usuario": [1, 2, 3, 4],
        "nombre_completo": ["Ana", "Luis", "Luis", "Pedro"],
        "vigente": [True, True, True, False],
    }))
    opciones = dashboard._opciones_colaborador()
    assert opciones["Todos"] == (None, True)
    assert opciones["Ana"] == (1, True)
    assert opciones["Luis (#2)"] == (2, True)      # nombres repetidos: se distinguen
    assert opciones["Luis (#3)"] == (3, True)
    assert opciones["Pedro — inactivo"] == (4, False)


def test_el_filtro_de_tipo_ofrece_todo_el_catalogo(monkeypatch):
    monkeypatch.setattr(dashboard, "listar_motivos", lambda: pd.DataFrame({
        "nombre": ["VACACION", "DUELO", "MATRIMONIO"]}))
    df = pd.DataFrame({"tipo_ausencia": ["VACACION", "MOTIVO ANTIGUO"]})
    opciones = dashboard._opciones_tipo(df)
    assert opciones[0] == "Todos"
    assert opciones[1:4] == ["VACACION", "DUELO", "MATRIMONIO"]  # aunque no tengan solicitudes
    assert "MOTIVO ANTIGUO" in opciones                            # y los ya usados


# ---------------------------------------------------------------------------
# Soporte
# ---------------------------------------------------------------------------
class _St:
    def __init__(self):
        self.html = []

    def markdown(self, texto, unsafe_allow_html=False):
        self.html.append(texto)


def test_el_pie_incluye_el_contacto_de_soporte(monkeypatch):
    falso = _St()
    monkeypatch.setattr(estilos, "st", falso)
    estilos.pie_de_pagina()
    html = falso.html[0]
    assert "soporte-it@setesagt.com" in html and "mailto:" in html
    assert "Solo IT puede restablecer contraseñas y desbloquear accesos" in html


def test_el_correo_de_soporte_se_puede_configurar(monkeypatch):
    from src.core import config

    monkeypatch.setattr(config, "obtener_variable", lambda n: "ayuda@setesa.example")
    assert config.soporte_correo() == "ayuda@setesa.example"
    monkeypatch.setattr(config, "obtener_variable", lambda n: None)
    assert config.soporte_correo() == "soporte-it@setesagt.com"


def test_el_mensaje_de_bloqueo_indica_a_quien_acudir():
    assert "soporte-it@setesagt.com" in str(intentos.CuentaBloqueada(15))


# ---------------------------------------------------------------------------
# Cambio de contraseña
# ---------------------------------------------------------------------------
def test_la_confirmacion_debe_coincidir():
    with pytest.raises(cuenta.PasswordError, match="no coinciden"):
        cuenta.cambiar_password(1, "Actual123", "Nueva1234", "Otra12345")


@pytest.mark.parametrize("nueva", ["corta1", "solo letras sin numero", "12345678"])
def test_la_contrasena_nueva_cumple_la_politica(nueva):
    with pytest.raises(cuenta.PasswordError):
        cuenta.cambiar_password(1, "Actual123", nueva, nueva)


def test_la_nueva_debe_ser_distinta_de_la_actual():
    with pytest.raises(cuenta.PasswordError, match="distinta"):
        cuenta.cambiar_password(1, "Actual123", "Actual123", "Actual123")


@pytest.fixture
def mundo_cuenta(monkeypatch):
    """Usuario temporal en una transacción que se revierte (incluye la columna nueva)."""
    from scripts.migracion_fase24 import DDL
    from src.core.security import hash_password
    from transaccion import transaccion_revertida

    with transaccion_revertida(monkeypatch, cuenta, ddl=DDL) as cursor:
        correo = f"pytest_cuenta_{uuid4().hex[:8]}@example.com"
        cursor.execute(
            """
            INSERT INTO usuario (id_rol, nombre_completo, correo_institucional,
                                 password_hash, estado_vigencia, ultima_actividad,
                                 debe_cambiar_password)
            SELECT id_rol, 'PYTEST Cuenta', %s, %s, TRUE, NOW(), TRUE
              FROM rol WHERE nombre_rol = 'Consultor' RETURNING id_usuario
            """,
            (correo, hash_password("Temporal123")),
        )
        yield {"cursor": cursor, "id": cursor.fetchone()[0], "correo": correo}


@requiere_bd
def test_el_cambio_exige_la_contrasena_actual_y_cuenta_los_fallos(mundo_cuenta):
    c = mundo_cuenta
    assert cuenta.requiere_cambio(c["id"]) is True
    with pytest.raises(cuenta.PasswordError, match="no es correcta"):
        cuenta.cambiar_password(c["id"], "equivocada1", "NuevaClave123", "NuevaClave123")
    c["cursor"].execute("SELECT intentos FROM intento_login WHERE correo = %s", (c["correo"],))
    assert c["cursor"].fetchone()[0] == 1
    assert cuenta.requiere_cambio(c["id"]) is True  # no cambió


@requiere_bd
def test_cambiar_la_contrasena_quita_la_marca_y_queda_auditado(mundo_cuenta):
    from src.core.security import verify_password

    c = mundo_cuenta
    cuenta.cambiar_password(c["id"], "Temporal123", "MiClaveNueva9", "MiClaveNueva9")
    assert cuenta.requiere_cambio(c["id"]) is False

    c["cursor"].execute("SELECT password_hash FROM usuario WHERE id_usuario = %s", (c["id"],))
    nuevo_hash = c["cursor"].fetchone()[0]
    assert verify_password("MiClaveNueva9", nuevo_hash)
    assert not verify_password("Temporal123", nuevo_hash)

    c["cursor"].execute(
        "SELECT COUNT(*) FROM usuario_log WHERE id_afectado = %s AND accion = 'CAMBIO_PASSWORD'",
        (c["id"],))
    assert c["cursor"].fetchone()[0] == 1


@requiere_bd
def test_los_fallos_al_cambiar_cuentan_para_el_bloqueo(mundo_cuenta):
    c = mundo_cuenta
    for _ in range(intentos.MAX_INTENTOS):
        with pytest.raises(cuenta.PasswordError):
            cuenta.cambiar_password(c["id"], "equivocada1", "NuevaClave123", "NuevaClave123")
    with pytest.raises(cuenta.PasswordError, match="bloqueado"):
        cuenta.cambiar_password(c["id"], "Temporal123", "NuevaClave123", "NuevaClave123")


@requiere_bd
def test_las_cuentas_nuevas_y_los_reinicios_de_it_exigen_el_cambio(monkeypatch):
    from scripts.migracion_fase18 import DDL as DDL18
    from scripts.migracion_fase24 import DDL
    from src.core import gestion_usuarios
    from transaccion import transaccion_revertida

    with transaccion_revertida(monkeypatch, gestion_usuarios, cuenta, ddl=[*DDL18, *DDL]) as cursor:
        cursor.execute(
            """
            INSERT INTO usuario (id_rol, nombre_completo, correo_institucional,
                                 password_hash, estado_vigencia, ultima_actividad)
            SELECT id_rol, 'PYTEST IT', 'pytest_it_' || md5(random()::text),
                   'x', TRUE, NOW() FROM rol WHERE nombre_rol = 'IT' RETURNING id_usuario
            """
        )
        it = cursor.fetchone()[0]
        correo = f"pytest_nuevo_{uuid4().hex[:8]}@example.com"
        gestion_usuarios.crear_usuario(it, "PYTEST Nuevo", correo, "Consultor", "Inicial1234")
        cursor.execute("SELECT id_usuario, debe_cambiar_password FROM usuario "
                       "WHERE correo_institucional = %s", (correo,))
        nuevo, marcado = cursor.fetchone()
        assert marcado is True

        cursor.execute("UPDATE usuario SET debe_cambiar_password = FALSE WHERE id_usuario = %s", (nuevo,))
        gestion_usuarios.resetear_password(it, nuevo, "Temporal5678")
        assert cuenta.requiere_cambio(nuevo) is True


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------
@requiere_bd
def test_con_contrasena_temporal_solo_se_ve_el_cambio_obligatorio():
    from streamlit.testing.v1 import AppTest

    ruta = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")
    conn = database.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT u.id_usuario, u.nombre_completo FROM usuario u JOIN rol r USING (id_rol) "
                "WHERE r.nombre_rol = 'Consultor' AND u.estado_vigencia LIMIT 1")
            fila = cursor.fetchone()
    finally:
        conn.close()
    if not fila:
        pytest.skip("No hay un consultor vigente.")

    at = AppTest.from_file(ruta, default_timeout=60)
    at.session_state["logged_in"] = True
    at.session_state["id_usuario"] = fila[0]
    at.session_state["nombre"] = fila[1]
    at.session_state["rol"] = "Consultor"
    at.session_state["debe_cambiar_password"] = True
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    textos = " ".join(m.value for m in at.markdown)
    assert "Cambio de contraseña obligatorio" in textos
    assert "soporte-it@setesagt.com" in textos
    assert "Panel Operativo" not in textos          # no entra a nada más
    assert not at.sidebar.radio                       # ni al menú
