# Logging centralizado de la aplicación (H-23).
#
# Escribe en storage/logs/setesa.log con rotación y, además, en la consola.
# Los módulos de núcleo usan `obtener_logger()` en lugar de imprimir o de
# depender de Streamlit para registrar errores.

import logging
from logging.handlers import RotatingFileHandler

from src.core.config import STORAGE_DIR

LOG_DIR = STORAGE_DIR / "logs"
FORMATO = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_configurado = False


def configurar_logging(nivel=logging.INFO):
    """Configura una sola vez el logger raíz del proyecto."""
    global _configurado

    logger = logging.getLogger("setesa")
    if _configurado:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(nivel)
    logger.propagate = False

    if not logger.handlers:
        archivo = RotatingFileHandler(
            LOG_DIR / "setesa.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        archivo.setFormatter(logging.Formatter(FORMATO))
        logger.addHandler(archivo)

        consola = logging.StreamHandler()
        consola.setFormatter(logging.Formatter(FORMATO))
        logger.addHandler(consola)

    _configurado = True
    return logger


def obtener_logger(nombre="setesa"):
    """Devuelve un logger ya configurado para el módulo solicitado."""
    configurar_logging()
    return logging.getLogger(nombre)
