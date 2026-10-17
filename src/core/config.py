# Rutas centralizadas del proyecto.

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = PROJECT_ROOT / "storage"
PDF_DIR = STORAGE_DIR / "pdf"
FIRMAS_DIR = STORAGE_DIR / "firmas"


def ensure_dirs():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    FIRMAS_DIR.mkdir(parents=True, exist_ok=True)
