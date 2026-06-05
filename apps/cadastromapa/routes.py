import re
import unicodedata

from flask import Blueprint, jsonify, render_template, request, send_file

from apps.comum.seguranca import acesso_aplicacao_obrigatorio
from apps.cadastromapa.servicos import (
    extrair_dados_cadastro_mapa,
    gerar_planilha_cadastro_mapa,
)

ENDPOINT_ACESSO_CADASTRO_MAPA = "cadastromapa.exibir_cadastro_mapa"


cadastromapa_bp = Blueprint(
    "cadastromapa",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="static",
    url_prefix="/cadastromapa",
)


@cadastromapa_bp.get("/")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_MAPA)
def exibir_cadastro_mapa():
    return render_template(
        "cadastromapa/index.html",
        titulo_pagina="Cadastro Mapa",
    )


@cadastromapa_bp.post("/importar-mapa-cliente")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_MAPA)
def importar_cadastro_mapa_cliente():
    arquivo_pdf = request.files.get("pdf")

    if not arquivo_pdf:
        return jsonify({"erro": "Arquivo nao enviado."}), 400

    try:
        dados = extrair_dados_cadastro_mapa(arquivo_pdf)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify(dados)


@cadastromapa_bp.post("/exportar-excel")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_MAPA)
def exportar_excel():
    dados = request.get_json(silent=True) or {}
    paginas = dados.get("paginas") or []

    if not paginas:
        return jsonify({"erro": "Nenhuma parcela selecionada para exportacao."}), 400

    arquivo = gerar_planilha_cadastro_mapa(paginas)
    nome_arquivo = montar_nome_arquivo_leilao(paginas)
    return send_file(
        arquivo,
        as_attachment=True,
        download_name=nome_arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def montar_nome_arquivo_leilao(paginas):
    leilao = next(
        (str(pagina.get("leilao", "")).strip() for pagina in paginas if pagina.get("leilao")),
        "cadastro-mapa",
    )
    nome = unicodedata.normalize("NFKD", leilao)
    nome = "".join(caractere for caractere in nome if not unicodedata.combining(caractere))
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip(" .")

    return f"{nome or 'cadastro-mapa'}.xlsx"
