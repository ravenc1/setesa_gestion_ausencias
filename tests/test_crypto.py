# Pruebas unitarias del cifrado en reposo (H-11 / D-05).

import pandas as pd
import pytest
from cryptography.fernet import Fernet

from src.core.crypto import (
    CifradoError,
    cifrar,
    cifrar_campos,
    descifrar,
    descifrar_campos,
    descifrar_dataframe,
    es_cifrado,
)


def test_roundtrip_de_texto_sensible():
    texto = "Licencia médica por cirugía"
    cifrado = cifrar(texto)

    assert cifrado != texto
    assert es_cifrado(cifrado)
    assert descifrar(cifrado) == texto


def test_no_recifra_un_valor_ya_cifrado():
    cifrado = cifrar("secreto")
    assert cifrar(cifrado) == cifrado


def test_texto_heredado_en_claro_se_devuelve_intacto():
    assert descifrar("texto plano") == "texto plano"
    assert not es_cifrado("texto plano")


def test_none_y_vacios_no_se_cifran():
    assert cifrar(None) is None
    assert descifrar(None) is None
    assert cifrar("") == ""
    assert descifrar("") == ""


def test_sin_clave_falla_con_mensaje_claro(monkeypatch):
    monkeypatch.delenv("FERNET_KEY", raising=False)
    with pytest.raises(CifradoError, match="FERNET_KEY"):
        cifrar("secreto")


def test_clave_distinta_no_puede_descifrar(monkeypatch):
    cifrado = cifrar("secreto")
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())

    with pytest.raises(CifradoError, match="no coincide"):
        descifrar(cifrado)


def test_campos_de_diccionario():
    datos = {
        "explicacion": "motivo",
        "firma_empleado": "abc",
        "otro": "sin cifrar",
    }
    cifrados = cifrar_campos(datos)

    assert es_cifrado(cifrados["explicacion"])
    assert es_cifrado(cifrados["firma_empleado"])
    assert cifrados["otro"] == "sin cifrar"
    assert descifrar_campos(cifrados) == datos


def test_dataframe_descifra_y_conserva_nan():
    df = pd.DataFrame(
        {
            "explicacion": [cifrar("motivo"), None],
            "firma_gerencia": [None, cifrar("abc")],
        }
    )

    plano = descifrar_dataframe(df)

    assert plano.loc[0, "explicacion"] == "motivo"
    assert pd.isna(plano.loc[1, "explicacion"])
    assert plano.loc[1, "firma_gerencia"] == "abc"
