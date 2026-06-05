from apps.cadastroboleto.repository.cliente_repository import listar_clientes

def obter_clientes():
    dados = listar_clientes()

    resultado = [
        {
            "cnpj": str(item["cnpj"]).strip(),
            "descricao": item["nome"],
        }
        for item in dados
    ]

    return resultado
