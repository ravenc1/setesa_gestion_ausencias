# Configuración común de pytest: agrega la raíz del proyecto al sys.path
# y carga las variables de entorno para las pruebas de integración.

import sys
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

load_dotenv(RAIZ / ".env")
