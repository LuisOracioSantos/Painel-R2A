import os
import sys
from pathlib import Path


def runtime_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-this-secret-key")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 30 * 1024 * 1024))
    ALLOWED_EXTENSIONS = {"pdf"}
    BASE_DIR = runtime_base_dir()
    UPLOAD_FOLDER = BASE_DIR / "instance" / "cadastrocomissao" / "uploads"
    EXTRACTION_FOLDER = BASE_DIR / "instance" / "cadastrocomissao" / "extractions"
    EXPORT_FOLDER = BASE_DIR / "instance" / "cadastrocomissao" / "exports"

    @classmethod
    def init_app(cls, app):
        cls.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.EXTRACTION_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.EXPORT_FOLDER.mkdir(parents=True, exist_ok=True)
