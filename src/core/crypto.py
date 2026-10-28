# Cifrado en reposo de datos sensibles (H-11 / decisión D-05).
#
# Fernet (AES-128-CBC + HMAC-SHA256) cifra la explicación y las firmas antes de
# escribirlas en PostgreSQL. El prefijo "fernet:" distingue los datos cifrados
# de los registros heredados en texto claro, de modo que la lectura sigue
# funcionando durante y después de la migración.

import math

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

from src.core.config import obtener_variable

load_dotenv()

PREFIJO = "fernet:"
CAMPOS_SENSIBLES = (
    "explicacion",
    "firma_empleado",
    "firma_jefe_gtc",
    "firma_gerencia",
)


class CifradoError(Exception):
    """No se pudo cifrar o descifrar un dato sensible."""


def _clave():
    valor = obtener_variable("FERNET_KEY")
    if not valor:
        raise CifradoError(
            "Falta FERNET_KEY en .env o en los secrets de Streamlit. "
            "Genérela con: python -c \"from cryptography.fernet import "
            "Fernet; print(Fernet.generate_key().decode())\""
        )
    return valor.encode()


def es_cifrado(valor):
    """Indica si el valor ya está cifrado con el prefijo de la aplicación."""
    return isinstance(valor, str) and valor.startswith(PREFIJO)


def cifrar(valor):
    """Cifra un texto. Devuelve None/vacíos sin cambios y no recifra."""
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return valor
    if es_cifrado(valor):
        return valor

    texto = str(valor)
    if not texto:
        return texto

    try:
        token = Fernet(_clave()).encrypt(texto.encode("utf-8"))
    except CifradoError:
        raise
    except Exception as e:
        raise CifradoError(f"No se pudo cifrar el dato: {e}") from e
    return PREFIJO + token.decode("ascii")


def descifrar(valor):
    """Descifra un valor propio y deja intactos los heredados en claro."""
    if not es_cifrado(valor):
        return valor

    try:
        token = valor[len(PREFIJO):].encode("ascii")
        return Fernet(_clave()).decrypt(token).decode("utf-8")
    except InvalidToken as e:
        raise CifradoError(
            "No se pudo descifrar el dato: la FERNET_KEY no coincide."
        ) from e
    except CifradoError:
        raise
    except Exception as e:
        raise CifradoError(f"No se pudo descifrar el dato: {e}") from e


def cifrar_campos(datos):
    """Cifra los campos sensibles de un diccionario de solicitud."""
    if not datos:
        return datos

    copia = dict(datos)
    for campo in CAMPOS_SENSIBLES:
        if campo in copia:
            copia[campo] = cifrar(copia[campo])
    return copia


def descifrar_campos(datos):
    """Descifra los campos sensibles de un diccionario de solicitud."""
    if not datos:
        return datos

    copia = dict(datos)
    for campo in CAMPOS_SENSIBLES:
        if campo in copia:
            copia[campo] = descifrar(copia[campo])
    return copia


def _descifrar_celda(valor):
    if not isinstance(valor, str):
        return valor
    return descifrar(valor)


def descifrar_dataframe(df, columnas=CAMPOS_SENSIBLES):
    """Descifra las columnas sensibles de un DataFrame sin tocar los NaN."""
    if df is None or df.empty:
        return df

    copia = df.copy()
    for campo in columnas:
        if campo in copia.columns:
            copia[campo] = copia[campo].map(_descifrar_celda)
    return copia
