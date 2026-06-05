import os
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from flask import g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BASE_DIR = Path(__file__).resolve().parent
SQL_DIR = BASE_DIR / "sql"


class BancoLegadoNaoConfigurado(RuntimeError):
    pass


def obter_database_url():
    url_banco = os.getenv("CADASTRO_BOLETO_DATABASE_URL") or os.getenv("LEGADO_DATABASE_URL")

    if not url_banco:
        raise BancoLegadoNaoConfigurado(
            "Configure CADASTRO_BOLETO_DATABASE_URL ou LEGADO_DATABASE_URL para consultar o banco legado."
        )

    return url_banco


@lru_cache(maxsize=1)
def obter_engine():
    return create_engine(
        obter_database_url(),
        pool_pre_ping=True,
        pool_recycle=3600,
    )


@lru_cache(maxsize=1)
def obter_sessionmaker():
    return sessionmaker(bind=obter_engine())


def get_db():
    if "db_sqlserver" not in g:
        g.db_sqlserver = obter_sessionmaker()()

    return g.db_sqlserver


def close_session(exception=None):
    db = g.pop("db_sqlserver", None)

    if db is not None:
        db.close()


def load_sql(nome):
    return (SQL_DIR / nome).read_text(encoding="utf-8")


def normalizar_linha(linha):
    return {
        chave: normalizar_valor(valor)
        for chave, valor in linha.items()
    }


def normalizar_valor(valor):
    if isinstance(valor, Decimal):
        return float(valor)

    if isinstance(valor, (date, datetime)):
        return valor.isoformat()

    return valor


def init_app(app):
    app.teardown_appcontext(close_session)
