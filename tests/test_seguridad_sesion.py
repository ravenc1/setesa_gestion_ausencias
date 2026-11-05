# Fase 20: expiración de sesión y límite de intentos de acceso.

import datetime
import os
from uuid import uuid4

import pytest

from src.core import auth, intentos, sesion
from src.core.security import hash_password

AHORA = datetime.datetime(2026, 11, 5, 10, 0, 0)
IDLE = datetime.timedelta(minutes=30)
MAXIMO = datetime.timedelta(hours=8)


# ---------------------------------------------------------------------------
# Expiración de sesión
# ---------------------------------------------------------------------------
def _estado(inicio, ultima):
    return {sesion.CLAVE_INICIO: inicio, sesion.CLAVE_ULTIMA: ultima}


def _motivo(estado, ahora):
    return sesion.motivo_expiracion(estado, ahora, IDLE, MAXIMO)


def test_sesion_activa_no_expira():
    estado = _estado(AHORA - datetime.timedelta(hours=1),
                     AHORA - datetime.timedelta(minutes=10))
    assert _motivo(estado, AHORA) is None


def test_expira_por_inactividad():
    estado = _estado(AHORA - datetime.timedelta(hours=1),
                     AHORA - datetime.timedelta(minutes=31))
    assert _motivo(estado, AHORA) == sesion.MOTIVO_INACTIVIDAD


def test_expira_por_duracion_aunque_haya_actividad():
    estado = _estado(AHORA - datetime.timedelta(hours=8, minutes=1),
                     AHORA - datetime.timedelta(seconds=5))
    assert _motivo(estado, AHORA) == sesion.MOTIVO_DURACION


def test_la_interaccion_renueva_la_inactividad_pero_no_la_duracion():
    estado = _estado(AHORA - datetime.timedelta(hours=2),
                     AHORA - datetime.timedelta(minutes=29))
    sesion.registrar_interaccion(estado, AHORA)
    assert estado[sesion.CLAVE_ULTIMA] == AHORA
    assert estado[sesion.CLAVE_INICIO] == AHORA - datetime.timedelta(hours=2)


def test_sesion_sin_marcas_se_considera_nueva():
    estado = {}
    assert _motivo(estado, AHORA) is None
    assert estado[sesion.CLAVE_INICIO] == AHORA


def test_plazos_configurables(monkeypatch):
    monkeypatch.setattr(sesion, "obtener_variable", lambda n: {
        "SESSION_IDLE_MINUTES": "5", "SESSION_MAX_HOURS": "1"}.get(n))
    assert sesion.limite_inactividad() == datetime.timedelta(minutes=5)
    assert sesion.limite_duracion() == datetime.timedelta(hours=1)
    monkeypatch.setattr(sesion, "obtener_variable", lambda n: "no-es-numero")
    assert sesion.limite_inactividad() == datetime.timedelta(minutes=30)
    monkeypatch.setattr(sesion, "obtener_variable", lambda n: "-3")
    assert sesion.limite_duracion() == datetime.timedelta(hours=8)


def test_mensajes_de_expiracion():
    assert "inactividad" in sesion.mensaje_expiracion(sesion.MOTIVO_INACTIVIDAD)
    assert "duración máxima" in sesion.mensaje_expiracion(sesion.MOTIVO_DURACION)


# ---------------------------------------------------------------------------
# Límite de intentos (cursor simulado)
# ---------------------------------------------------------------------------
class _Cursor:
    def __init__(self, filas):
        self.filas = list(filas)
        self.sentencias = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.sentencias.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.filas.pop(0) if self.filas else None


def test_correo_se_normaliza():
    assert intentos.normalizar("  Ana@Example.COM ") == "ana@example.com"
    assert intentos.normalizar(None) == ""


def test_sin_bloqueo_no_hay_minutos():
    assert intentos.minutos_restantes(_Cursor([None]), "ana@example.com") == 0


def test_bloqueo_vigente_devuelve_minutos():
    assert intentos.minutos_restantes(_Cursor([(12,)]), "ana@example.com") == 12


def test_el_quinto_fallo_bloquea():
    cursor = _Cursor([(intentos.MAX_INTENTOS,)])
    assert intentos.registrar_fallo(cursor, "Ana@Example.com") == intentos.MAX_INTENTOS
    assert any(s.startswith("UPDATE intento_login SET bloqueado_hasta")
               for s, _ in cursor.sentencias)


def test_antes_del_maximo_no_bloquea():
    cursor = _Cursor([(intentos.MAX_INTENTOS - 1,)])
    intentos.registrar_fallo(cursor, "ana@example.com")
    assert not any(s.startswith("UPDATE intento_login")
                   for s, _ in cursor.sentencias)


def test_mensaje_de_cuenta_bloqueada():
    assert "15 minuto" in str(intentos.CuentaBloqueada(15))


# ---------------------------------------------------------------------------
# Integración con Supabase: todo ocurre en UNA transacción que se revierte
# (incluida la tabla nueva), así no queda nada guardado en la base.
# ---------------------------------------------------------------------------
requiere_bd = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requiere DATABASE_URL."
)


class _ConexionTransaccional:
    """Envuelve una conexión real: commit y close no hacen nada."""

    def __init__(self, conexion):
        self._conexion = conexion

    def cursor(self):
        return self._conexion.cursor()

    def commit(self):
        pass

    def close(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _crear_usuario(cursor, rol, correo, clave):
    cursor.execute("SELECT id_rol FROM rol WHERE nombre_rol = %s", (rol,))
    fila = cursor.fetchone()
    if not fila:
        pytest.skip(f"No existe el rol {rol}.")
    cursor.execute(
        """
        INSERT INTO usuario
            (id_rol, nombre_completo, correo_institucional,
             password_hash, estado_vigencia, ultima_actividad)
        VALUES (%s, %s, %s, %s, TRUE, NOW())
        RETURNING id_usuario
        """,
        (fila[0], f"PYTEST {rol}", correo, hash_password(clave)),
    )
    return cursor.fetchone()[0]


@pytest.fixture
def entorno(monkeypatch):
    import psycopg2

    from scripts.migracion_fase20 import DDL

    real = psycopg2.connect(os.environ["DATABASE_URL"])
    cursor = real.cursor()
    try:
        for sentencia in DDL:
            cursor.execute(sentencia)
        sufijo = uuid4().hex[:8]
        clave = "ClaveCorrecta123"
        datos = {
            "correo": f"pytest_intentos_{sufijo}@example.com",
            "clave": clave,
            "cursor": cursor,
        }
        datos["id_usuario"] = _crear_usuario(
            cursor, "Consultor", datos["correo"], clave
        )
        datos["id_it"] = _crear_usuario(
            cursor, "IT", f"pytest_it_{sufijo}@example.com", clave
        )
        proxy = _ConexionTransaccional(real)
        monkeypatch.setattr(auth, "get_connection", lambda: proxy)
        from src.core import gestion_usuarios

        monkeypatch.setattr(gestion_usuarios, "get_connection", lambda: proxy)
        yield datos
    finally:
        real.rollback()
        cursor.close()
        real.close()


@requiere_bd
def test_cinco_fallos_bloquean_aun_con_la_clave_correcta(entorno):
    for _ in range(intentos.MAX_INTENTOS):
        assert auth.login_user(entorno["correo"], "incorrecta") is None
    with pytest.raises(intentos.CuentaBloqueada):
        auth.login_user(entorno["correo"], entorno["clave"])


@requiere_bd
def test_un_acceso_correcto_reinicia_el_conteo(entorno):
    correo, clave = entorno["correo"], entorno["clave"]
    for _ in range(intentos.MAX_INTENTOS - 1):
        assert auth.login_user(correo, "incorrecta") is None
    assert auth.login_user(correo, clave) is not None

    # El conteo volvió a cero: otros 4 fallos no bloquean.
    for _ in range(intentos.MAX_INTENTOS - 1):
        assert auth.login_user(correo, "incorrecta") is None
    assert auth.login_user(correo, clave) is not None


@requiere_bd
def test_correo_inexistente_tambien_se_bloquea_sin_revelarlo(entorno):
    fantasma = "no.existe." + entorno["correo"]
    for _ in range(intentos.MAX_INTENTOS):
        assert auth.login_user(fantasma, "x") is None
    with pytest.raises(intentos.CuentaBloqueada):
        auth.login_user(fantasma, "x")


@requiere_bd
def test_el_bloqueo_vence_y_el_conteo_se_reinicia(entorno):
    correo, clave, cursor = entorno["correo"], entorno["clave"], entorno["cursor"]
    for _ in range(intentos.MAX_INTENTOS):
        auth.login_user(correo, "incorrecta")
    # Se simula que el bloqueo ya cumplió su plazo.
    cursor.execute(
        "UPDATE intento_login SET bloqueado_hasta = NOW() - INTERVAL '1 minute', "
        "ultimo_intento = NOW() - INTERVAL '16 minutes' WHERE correo = %s",
        (correo,),
    )
    assert auth.login_user(correo, "incorrecta") is None  # ya no está bloqueado
    cursor.execute("SELECT intentos FROM intento_login WHERE correo = %s", (correo,))
    assert cursor.fetchone()[0] == 1
    assert auth.login_user(correo, clave) is not None


@requiere_bd
def test_it_desbloquea_y_queda_auditado(entorno):
    from src.core.gestion_usuarios import desbloquear_acceso, GestionUsuariosError

    correo, clave, cursor = entorno["correo"], entorno["clave"], entorno["cursor"]
    for _ in range(intentos.MAX_INTENTOS):
        auth.login_user(correo, "incorrecta")
    assert intentos.minutos_restantes(cursor, correo) > 0

    desbloquear_acceso(entorno["id_it"], correo)
    assert intentos.minutos_restantes(cursor, correo) == 0
    assert auth.login_user(correo, clave) is not None

    cursor.execute(
        "SELECT COUNT(*) FROM usuario_log WHERE id_afectado = %s "
        "AND accion = 'DESBLOQUEO'", (entorno["id_usuario"],))
    assert cursor.fetchone()[0] == 1
    with pytest.raises(GestionUsuariosError):  # ya no hay bloqueo que levantar
        desbloquear_acceso(entorno["id_it"], correo)


@requiere_bd
def test_solo_it_puede_desbloquear(entorno):
    from src.core.gestion_usuarios import OperacionNoPermitida, desbloquear_acceso

    auth.login_user(entorno["correo"], "incorrecta")
    with pytest.raises(OperacionNoPermitida):
        desbloquear_acceso(entorno["id_usuario"], entorno["correo"])
