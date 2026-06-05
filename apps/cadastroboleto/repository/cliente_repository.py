from sqlalchemy import text

from apps.cadastroboleto.db import load_sql, normalizar_linha, obter_engine

def listar_clientes():
    query = load_sql("busca_cliente.sql")

    with obter_engine().connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchall()

    return [normalizar_linha(row._mapping) for row in rows]
