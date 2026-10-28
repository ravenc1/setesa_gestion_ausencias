# Pruebas unitarias de las utilidades de firma (no requieren base de datos).

import base64
import io

import numpy as np
from PIL import Image

from src.services.utils_firma import (
    base64_to_image,
    canvas_to_base64,
    eliminar_archivo,
)


def _png_b64():
    img = Image.new("RGB", (60, 20), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_base64_to_image_genera_nombres_unicos():
    primera = base64_to_image(_png_b64())
    segunda = base64_to_image(_png_b64())
    try:
        assert primera and segunda
        assert primera != segunda, "Dos firmas no deben compartir archivo temporal"
    finally:
        eliminar_archivo(primera)
        eliminar_archivo(segunda)


def test_eliminar_archivo_es_idempotente():
    ruta = base64_to_image(_png_b64())
    assert eliminar_archivo(ruta) is True
    assert eliminar_archivo(ruta) is True  # ya no existe, no debe fallar
    assert eliminar_archivo(None) is False


def test_base64_invalido_devuelve_none():
    assert base64_to_image("") is None
    assert base64_to_image("   ") is None


def test_canvas_vacio_devuelve_none():
    canvas_vacio = np.zeros((100, 300, 4), dtype=np.uint8)
    assert canvas_to_base64(canvas_vacio) is None


def test_canvas_con_trazo_devuelve_png_base64():
    canvas = np.zeros((100, 300, 4), dtype=np.uint8)
    canvas[40:60, 100:200, 3] = 255  # trazo opaco
    resultado = canvas_to_base64(canvas)
    assert resultado
    contenido = base64.b64decode(resultado)
    assert contenido.startswith(b"\x89PNG")
