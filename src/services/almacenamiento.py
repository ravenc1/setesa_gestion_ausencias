# Repositorio persistente de expedientes (Fase 17, tesis objetivo d).
#
# Render borra su disco en cada despliegue o reinicio, así que los PDF
# oficiales (y en la Fase 18 las evidencias) se guardan en un bucket PRIVADO
# de Supabase Storage. Sin esa configuración se usa la carpeta local
# storage/repositorio/, útil para desarrollo y pruebas.
#
# Configuración (.env o variables del servidor; nunca en el repositorio):
#   SUPABASE_URL          https://<proyecto>.supabase.co
#   SUPABASE_SERVICE_KEY  llave secreta (service_role o sb_secret_...)
#   SUPABASE_BUCKET       opcional; por defecto "expedientes"
#
# Las claves de objeto son rutas relativas, p. ej. "pdf/12/final_ab12cd.pdf".

from pathlib import Path
from urllib.parse import quote

import requests

from src.core.config import STORAGE_DIR, obtener_variable

REPOSITORIO_DIR = STORAGE_DIR / "repositorio"
BUCKET_DEFAULT = "expedientes"
TIMEOUT_SEGUNDOS = 30
TAMANO_MAXIMO = 10 * 1024 * 1024  # 10 MB por archivo
TIPOS_PERMITIDOS = ["application/pdf", "image/jpeg", "image/png"]


class AlmacenamientoError(Exception):
    """No se pudo leer o escribir en el repositorio."""


class ArchivoNoEncontrado(AlmacenamientoError):
    """El objeto no existe en el repositorio."""


class ArchivoExistente(AlmacenamientoError):
    """El objeto ya existe y no se permite sobrescribirlo."""


def _validar_clave(clave):
    clave = (clave or "").strip().lstrip("/")
    if not clave or ".." in Path(clave).parts:
        raise AlmacenamientoError(f"Clave de archivo inválida: {clave!r}")
    return clave


def configuracion_supabase():
    """Datos de Supabase Storage, o None si no está configurado."""
    url = obtener_variable("SUPABASE_URL")
    llave = obtener_variable("SUPABASE_SERVICE_KEY")
    if not (url and llave):
        return None
    return {
        "url": url.rstrip("/"),
        "llave": llave,
        "bucket": obtener_variable("SUPABASE_BUCKET") or BUCKET_DEFAULT,
    }


def backend():
    """'supabase' si hay configuración; si no, 'local'."""
    return "supabase" if configuracion_supabase() else "local"


def _encabezados(llave, extra=None):
    # Las llaves nuevas (sb_secret_...) no son JWT: basta con "apikey". Las
    # heredadas (service_role, JWT) también van como Bearer.
    encabezados = {"apikey": llave}
    if llave.startswith("eyJ"):
        encabezados["Authorization"] = f"Bearer {llave}"
    encabezados.update(extra or {})
    return encabezados


def _url_objeto(config, clave):
    return (
        f"{config['url']}/storage/v1/object/{config['bucket']}/"
        f"{quote(clave, safe='/')}"
    )


# ---------------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------------
def guardar(clave, contenido, tipo="application/pdf", sobrescribir=True):
    """Guarda ``contenido`` (bytes) en ``clave``. Devuelve la clave."""
    clave = _validar_clave(clave)
    if len(contenido) > TAMANO_MAXIMO:
        raise AlmacenamientoError("El archivo supera el tamaño máximo permitido.")

    config = configuracion_supabase()
    if not config:
        destino = REPOSITORIO_DIR / clave
        if destino.exists() and not sobrescribir:
            raise ArchivoExistente(f"Ya existe {clave}.")
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_suffix(destino.suffix + ".tmp")
        temporal.write_bytes(contenido)
        temporal.replace(destino)
        return clave

    try:
        respuesta = requests.post(
            _url_objeto(config, clave),
            data=contenido,
            headers=_encabezados(
                config["llave"],
                {
                    "Content-Type": tipo,
                    "x-upsert": "true" if sobrescribir else "false",
                    "Cache-Control": "no-cache",
                },
            ),
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as e:
        raise AlmacenamientoError(f"No se pudo subir {clave}: {e}") from e

    if respuesta.status_code in (200, 201):
        return clave
    if respuesta.status_code == 409 or "Duplicate" in respuesta.text:
        raise ArchivoExistente(f"Ya existe {clave}.")
    raise AlmacenamientoError(
        f"Supabase Storage rechazó {clave} ({respuesta.status_code}): "
        f"{respuesta.text[:200]}"
    )


def leer(clave):
    """Devuelve los bytes de ``clave``. Lanza ArchivoNoEncontrado si falta."""
    clave = _validar_clave(clave)
    config = configuracion_supabase()
    if not config:
        origen = REPOSITORIO_DIR / clave
        if not origen.exists():
            raise ArchivoNoEncontrado(f"No existe {clave}.")
        return origen.read_bytes()

    try:
        respuesta = requests.get(
            _url_objeto(config, clave).replace(
                "/storage/v1/object/", "/storage/v1/object/authenticated/", 1
            ),
            headers=_encabezados(config["llave"]),
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as e:
        raise AlmacenamientoError(f"No se pudo descargar {clave}: {e}") from e

    if respuesta.status_code == 200:
        return respuesta.content
    if respuesta.status_code in (400, 404):
        raise ArchivoNoEncontrado(f"No existe {clave}.")
    raise AlmacenamientoError(
        f"Supabase Storage no entregó {clave} ({respuesta.status_code})."
    )


def existe(clave):
    try:
        leer(clave)
        return True
    except ArchivoNoEncontrado:
        return False


def crear_bucket():
    """Crea el bucket privado si no existe. Devuelve 'creado' o 'existente'."""
    config = configuracion_supabase()
    if not config:
        raise AlmacenamientoError(
            "Falta SUPABASE_URL o SUPABASE_SERVICE_KEY para crear el bucket."
        )
    respuesta = requests.post(
        f"{config['url']}/storage/v1/bucket",
        json={
            "id": config["bucket"],
            "name": config["bucket"],
            "public": False,
            "file_size_limit": TAMANO_MAXIMO,
            "allowed_mime_types": TIPOS_PERMITIDOS,
        },
        headers=_encabezados(config["llave"]),
        timeout=TIMEOUT_SEGUNDOS,
    )
    if respuesta.status_code in (200, 201):
        return "creado"
    if respuesta.status_code == 409 or "already exists" in respuesta.text:
        return "existente"
    raise AlmacenamientoError(
        f"No se pudo crear el bucket ({respuesta.status_code}): "
        f"{respuesta.text[:200]}"
    )
