import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
CAMINHO_BANCO_PADRAO = BASE_DIR / "instance" / "meu_painel.sqlite3"


def converter_para_booleano(valor, padrao=False):
    if valor is None:
        return padrao

    return str(valor).strip().lower() in {"1", "true", "sim", "s", "yes", "y", "on"}


class ConfiguracaoBase:
    APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "desenvolvimento")).lower()
    NOME_SISTEMA = os.getenv("NOME_SISTEMA", "Meu Painel Flask")
    SECRET_KEY = os.getenv("SECRET_KEY", "altere-esta-chave-em-producao")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + CAMINHO_BANCO_PADRAO.as_posix(),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    CRIAR_BANCO_AUTOMATICAMENTE = converter_para_booleano(
        os.getenv("CRIAR_BANCO_AUTOMATICAMENTE"),
        padrao=True,
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = converter_para_booleano(
        os.getenv("SESSION_COOKIE_SECURE"),
        padrao=False,
    )
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    ADMIN_PADRAO_NOME = os.getenv("ADMIN_PADRAO_NOME", "Administrador")
    ADMIN_PADRAO_EMAIL = os.getenv("ADMIN_PADRAO_EMAIL", "admin@local")
    ADMIN_PADRAO_SENHA = os.getenv("ADMIN_PADRAO_SENHA", "Admin@12345")
    TEMPLATES_AUTO_RELOAD = converter_para_booleano(
        os.getenv("TEMPLATES_AUTO_RELOAD"),
        padrao=True,
    )
    JSON_AS_ASCII = False


class ConfiguracaoDesenvolvimento(ConfiguracaoBase):
    DEBUG = True


class ConfiguracaoTeste(ConfiguracaoBase):
    TESTING = True
    DEBUG = False


class ConfiguracaoProducao(ConfiguracaoBase):
    DEBUG = False
    TEMPLATES_AUTO_RELOAD = False


CONFIGURACOES = {
    "desenvolvimento": ConfiguracaoDesenvolvimento,
    "development": ConfiguracaoDesenvolvimento,
    "teste": ConfiguracaoTeste,
    "testing": ConfiguracaoTeste,
    "producao": ConfiguracaoProducao,
    "production": ConfiguracaoProducao,
}


def obter_configuracao(nome_ambiente=None):
    ambiente = (
        nome_ambiente
        or os.getenv("APP_ENV")
        or os.getenv("FLASK_ENV")
        or "desenvolvimento"
    )
    return CONFIGURACOES.get(ambiente.lower(), ConfiguracaoDesenvolvimento)
