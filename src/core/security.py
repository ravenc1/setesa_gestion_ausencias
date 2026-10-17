# Seguridad: hashing de contraseñas y control de acceso por rol.

import hashlib
import hmac
import os

import streamlit as st

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 240000


def hash_password(password):
    """Genera un hash PBKDF2-SHA256 con sal aleatoria."""
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${derived.hex()}"


def es_hash(stored):
    """Indica si el valor almacenado ya está en formato de hash propio."""
    return isinstance(stored, str) and stored.startswith(f"{ALGORITHM}$")


def verify_password(password, stored):
    """Verifica una contraseña contra un hash almacenado."""
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(derived.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def verify_or_upgrade(password, stored):
    """Valida la contraseña soportando contraseñas heredadas en texto plano.

    Si la contraseña es correcta y estaba en texto plano, retorna el nuevo hash
    para que el llamador la actualice en la base de datos.
    """
    if es_hash(stored):
        return verify_password(password, stored), None
    if isinstance(stored, str) and hmac.compare_digest(stored, str(password)):
        return True, hash_password(password)
    return False, None


def rol_autorizado(roles):
    """RBAC: valida que el rol en sesión esté dentro de los roles permitidos."""
    return st.session_state.get("rol") in roles
