# Pruebas unitarias de hashing y migración de contraseñas.

from src.core.security import (
    ALGORITHM,
    es_hash,
    hash_password,
    verify_or_upgrade,
    verify_password,
)


def test_hash_tiene_formato_esperado():
    valor = hash_password("ClaveSegura123")
    assert valor.startswith(f"{ALGORITHM}$")
    assert len(valor.split("$")) == 4


def test_hash_es_aleatorio():
    assert hash_password("misma") != hash_password("misma")


def test_verificar_password_correcta_e_incorrecta():
    valor = hash_password("ClaveSegura123")
    assert verify_password("ClaveSegura123", valor)
    assert not verify_password("otra", valor)


def test_hash_malformado_no_revienta():
    assert not verify_password("x", "texto-plano")
    assert not verify_password("x", "pbkdf2_sha256$abc")
    assert not verify_password("x", None)


def test_es_hash():
    assert es_hash(hash_password("x"))
    assert not es_hash("texto-plano")
    assert not es_hash(None)


def test_verify_or_upgrade_migra_texto_plano():
    valido, nuevo_hash = verify_or_upgrade("clave-vieja", "clave-vieja")
    assert valido
    assert nuevo_hash is not None
    assert es_hash(nuevo_hash)
    assert verify_password("clave-vieja", nuevo_hash)


def test_verify_or_upgrade_no_rehashea_un_hash():
    valor = hash_password("clave")
    valido, nuevo_hash = verify_or_upgrade("clave", valor)
    assert valido
    assert nuevo_hash is None


def test_verify_or_upgrade_rechaza_clave_incorrecta():
    assert verify_or_upgrade("mala", "clave-vieja") == (False, None)
