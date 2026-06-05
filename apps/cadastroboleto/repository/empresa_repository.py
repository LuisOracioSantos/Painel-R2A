from sqlalchemy import text

from apps.cadastroboleto.db import load_sql, normalizar_linha, obter_engine

def buscar_contrato(cnpj):
    query = load_sql("busca_contrato.sql")
    with obter_engine().connect() as conn:
        result = conn.execute(text(query), {"cnpj": cnpj})
        return [normalizar_linha(row) for row in result.mappings().all()]


def buscar_parcelas(cnpj):
    query = load_sql("busca_parcelas_contratos.sql")
    with obter_engine().connect() as conn:
        result = conn.execute(text(query), {"cnpj": cnpj})
        return [normalizar_linha(row) for row in result.mappings().all()]
