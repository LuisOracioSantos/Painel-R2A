from apps.cadastroboleto.repository.empresa_repository import buscar_contrato, buscar_parcelas

def listar_dados_empresa(cnpj):
    contrato = buscar_contrato(cnpj)
    parcelas = buscar_parcelas(cnpj)

    return {
        "contrato": contrato,
        "parcelas": parcelas,
    }
