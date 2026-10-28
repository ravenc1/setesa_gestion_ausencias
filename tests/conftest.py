# Configuración común de pytest: agrega la raíz del proyecto al sys.path,
# carga las variables de entorno y garantiza una clave de cifrado para las
# pruebas (en producción se define en .env).

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

load_dotenv(RAIZ / ".env")

if not os.getenv("FERNET_KEY"):
    os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
