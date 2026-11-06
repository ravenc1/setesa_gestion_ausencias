# Fase 26: la app usa la hora de Guatemala aunque el servidor esté en UTC.
import os

import src.core.config  # noqa: F401  (fija TZ al importarse)


def test_zona_horaria_por_defecto_es_guatemala():
    assert os.environ.get("TZ") == "America/Guatemala"
