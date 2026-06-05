import io
import re

import fitz
import pandas as pd
from flask import Blueprint, jsonify, render_template, request, send_file

from apps.comum.seguranca import acesso_aplicacao_obrigatorio
from apps.cadastroboleto.db import BancoLegadoNaoConfigurado
from apps.cadastroboleto.service.cliente_service import obter_clientes
from apps.cadastroboleto.service.empresa_service import listar_dados_empresa


ENDPOINT_ACESSO_CADASTRO_BOLETO = "cadastroboleto.exibir_cadastro_boleto"

cadastroboleto_bp = Blueprint(
    "cadastroboleto",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="static",
    url_prefix="/cadastroboleto",
)

COLUNAS = [
    "chave_cliente", "contrato", "parcela", "venc_parcela", "cod_banco",
    "cod_carteira", "cod_cedente", "num_agencia", "conta_corrente",
    "nosso_numero", "vencimento_boleto", "valor_boleto", "% Multa Boleto", "% Juros Boleto", "data_documento",
    "linha_digitavel", "codigo_barras", "numero_documento", "instrucoes",
    "mensagens", "pix_copia_cola", "url",
]


@cadastroboleto_bp.get("/")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_BOLETO)
def exibir_cadastro_boleto():
    tabela_html = pd.DataFrame(columns=COLUNAS).to_html(
        classes="tabela-boletos",
        index=False,
    )
    return render_template(
        "cadastroboleto/index.html",
        texto="",
        tabela=tabela_html,
        titulo_pagina="Cadastro Boleto",
    )


@cadastroboleto_bp.post("/pdf")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_BOLETO)
def importar_pdf():
    arquivo = request.files.get("arquivo")

    if not arquivo or arquivo.filename == "":
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400

    texto = ""

    try:
        documento = fitz.open(stream=arquivo.read(), filetype="pdf")

        for pagina in documento:
            texto += pagina.get_text()
    except Exception as erro:
        return jsonify({"erro": f"Erro ao ler PDF: {erro}"}), 500

    blocos = re.split(r"(?=Codigo de Barras:|C.digo de Barras:)", texto)
    dados_pdf = []

    for bloco in blocos:
        if "Data vencimento" not in bloco:
            continue

        vencimento = re.search(r"Data vencimento:\s*(\d{2}/\d{2}/\d{4})", bloco)
        valor = re.search(r"Valor.*?:?\s*R?\$?\s*([\d\.,]+)", bloco, re.IGNORECASE)
        nosso_numero = re.search(r"Nosso n.mero:\s*(\d+(?:\.\d+)?-\d)", bloco)
        codigo_barras = re.search(r"C.digo de Barras:\s*(\d+)", bloco)
        linha_digitavel = re.search(r"Linha Digit.vel:\s*([\d\s]+)", bloco)
        juros = re.search(r"Juros\s*([\d\.,]+)%", bloco, re.IGNORECASE)
        multa = re.search(r"Multa\s*(?:de)?\s*([\d\.,]+)%", bloco, re.IGNORECASE)

        if not vencimento or not valor:
            continue

        dados_pdf.append({
            "vencimento": vencimento.group(1),
            "valor": float(valor.group(1).replace(".", "").replace(",", ".")),
            "nosso_numero": nosso_numero.group(1) if nosso_numero else None,
            "linha_digitavel": linha_digitavel.group(1) if linha_digitavel else None,
            "codigo_barras": codigo_barras.group(1) if codigo_barras else None,
            "juros": float(juros.group(1).replace(".", "").replace(",", ".")) if juros else None,
            "multa": float(multa.group(1).replace(".", "").replace(",", ".")) if multa else None,
        })

    return jsonify(dados_pdf)


@cadastroboleto_bp.get("/clientes")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_BOLETO)
def consultar_clientes():
    try:
        clientes = obter_clientes()
    except BancoLegadoNaoConfigurado as erro:
        return jsonify({"erro": str(erro), "clientes": []}), 501

    return jsonify(clientes)


@cadastroboleto_bp.get("/buscar-dados")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_BOLETO)
def buscar_dados_cliente():
    cnpj = request.args.get("cnpj", "").strip()

    if not cnpj:
        return jsonify({"erro": "CNPJ nao informado.", "parcelas": []}), 400

    try:
        dados_empresa = listar_dados_empresa(cnpj)
    except BancoLegadoNaoConfigurado as erro:
        return jsonify({"erro": str(erro), "parcelas": []}), 501

    return jsonify(dados_empresa)


@cadastroboleto_bp.post("/exportar-excel")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_BOLETO)
def exportar_excel():
    dados = request.get_json(silent=True)

    if not dados:
        return jsonify({"erro": "Nenhum dado recebido."}), 400

    df = pd.DataFrame(dados)
    df = df.rename(columns={
        "CPFCNPJ": "chave_cliente",
        "CONTRATO": "contrato",
        "NUMERO": "parcela",
        "VENCIMENTO": "venc_parcela",
        "VALOR": "valor_boleto",
        "multa": "% Multa Boleto",
        "juros": "% Juros Boleto",
        "agencia": "num_agencia",
        "conta_corrente": "conta_corrente",
        "nosso_numero": "nosso_numero",
        "vencimento_boleto": "vencimento_boleto",
        "linha_digitavel": "linha_digitavel",
        "codigo_barras": "codigo_barras",
        "pix_copia_cola": "pix_copia_cola",
        "url": "url",
        "mensagens": "mensagens",
        "instrucoes": "instrucoes",
        "numero_documento": "numero_documento",
    })

    for coluna in ("cod_banco", "cod_carteira", "cod_cedente"):
        df[coluna] = df.get(coluna, "")

    if "venc_parcela" in df.columns:
        df["venc_parcela"] = pd.to_datetime(df["venc_parcela"], errors="coerce").dt.strftime("%d/%m/%Y")

    if "vencimento_boleto" in df.columns:
        df["vencimento_boleto"] = pd.to_datetime(df["vencimento_boleto"], errors="coerce").dt.strftime("%d/%m/%Y")

    for coluna in COLUNAS:
        if coluna not in df.columns:
            df[coluna] = ""

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df[COLUNAS].to_excel(writer, index=False, sheet_name="Boletos")

    output.seek(0)

    return send_file(
        output,
        download_name="boletos.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@cadastroboleto_bp.post("/limpar")
@acesso_aplicacao_obrigatorio(ENDPOINT_ACESSO_CADASTRO_BOLETO)
def limpar_tabela():
    tabela_html = pd.DataFrame(columns=COLUNAS).to_html(
        classes="tabela-boletos",
        index=False,
    )
    return render_template(
        "cadastroboleto/index.html",
        tabela=tabela_html,
        titulo_pagina="Cadastro Boleto",
    )
