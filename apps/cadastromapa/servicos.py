import re
import unicodedata
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


BAIRRO_PADRAO = "Centro"
PALAVRAS_COMPLEMENTO = [
    "APTO",
    "APT",
    "BLOCO",
    "CJ",
    "CONJ",
    "CONJUNTO",
    "GALERIA",
    "LOTE",
    "QD",
    "QUADRA",
    "SALA",
]
PALAVRAS_IGNORAR_BAIRRO = [
    "CAIXA POSTAL",
    "CEP",
    "CHACARA",
    "ESTANCIA",
    "FAZENDA",
    "HARAS",
    "KM",
    "METRO",
    "RANCHO",
    "SITIO",
    "ZONA RURAL",
]
COLUNAS_EXPORTACAO = [
    ("leilao", "Leilao"),
    ("datacontrato", "Data Contrato"),
    ("produto", "Produto"),
    ("vendedor", "Vendedor"),
    ("comprador", "Comprador"),
    ("cpfcnpj", "CPF/CNPJ"),
    ("endereco", "Endereco"),
    ("numero", "Numero"),
    ("bairro", "Bairro"),
    ("cep", "CEP"),
    ("cidade", "Cidade"),
    ("uf", "UF"),
    ("complemento", "Complemento"),
    ("telefone1", "Telefone 1"),
    ("telefone2", "Telefone 2"),
    ("telefone3", "Telefone 3"),
    ("email1", "E-mail 1"),
    ("email2", "E-mail 2"),
    ("email3", "E-mail 3"),
    ("observacao", "Observacao"),
    ("parcela", "Numero Parcela"),
    ("vencimento", "Vencimento"),
    ("valor", "Valor"),
]


def extrair_dados_cadastro_mapa(arquivo_pdf):
    conteudo_pdf = arquivo_pdf.read()

    if not conteudo_pdf:
        raise ValueError("Arquivo PDF vazio.")

    try:
        import pymupdf
    except ImportError as erro:
        raise ValueError(
            "Dependencia PyMuPDF nao instalada. Execute: pip install -r requirements.txt"
        ) from erro

    try:
        documento_pdf = pymupdf.open(stream=conteudo_pdf, filetype="pdf")
    except Exception as erro:
        raise ValueError("Nao foi possivel abrir o PDF enviado.") from erro

    paginas = [
        extrair_dados_pagina(indice + 1, normalizar_espacos(pagina.get_text()))
        for indice, pagina in enumerate(documento_pdf)
    ]

    return {
        "total_paginas": len(paginas),
        "paginas": paginas,
    }


def extrair_dados_pagina(numero_pagina, texto):
    leilao, data_contrato = extrair_leilao(texto)
    comprador, cpf_cnpj = extrair_comprador(texto)
    vendedor = extrair_vendedor(texto)
    endereco = extrair_endereco(texto)
    logradouro, numero, cep, cidade, uf, bairro, complemento = tratar_endereco(endereco)
    telefones = re.findall(r"\(\d{2}\)\s*\d{4,5}-?\d+", texto)
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", texto)
    lotes = re.findall(r"\b(\d{1,5})\s+S\b", texto)
    lotes_texto = ", ".join(lotes) if lotes else ""

    return {
        "pagina": numero_pagina,
        "leilao": leilao,
        "datacontrato": data_contrato,
        "produto": "Duplicata",
        "comprador": comprador,
        "cpfcnpj": cpf_cnpj,
        "vendedor": vendedor,
        "endereco": logradouro,
        "numero": numero,
        "cep": cep,
        "cidade": cidade,
        "uf": uf,
        "bairro": bairro,
        "complemento": complemento,
        "telefones": telefones[:3],
        "emails": emails[:3],
        "observacao": f"{leilao} - Lote(s): {lotes_texto}",
        "parcelas": extrair_parcelas(texto),
    }


def normalizar_espacos(texto):
    return re.sub(r"\s+", " ", texto or "")


def extrair_leilao(texto):
    match = re.search(
        r"(.*?)\s*-\s*(\d{2}/\d{2}/\d{4})\s*Cadastro de Compradores",
        texto,
    )

    if not match:
        return "", ""

    nome_leilao = match.group(1).strip()
    data_contrato = match.group(2)

    for palavra in ["Leilao", "Leilão", "Virtual", "Nelore"]:
        nome_leilao = re.sub(rf"\b{palavra}\b", "", nome_leilao, flags=re.IGNORECASE)

    nome_leilao = re.sub(r"\s{2,}", " ", nome_leilao)
    nome_leilao = re.sub(r"\s*-\s*", " - ", nome_leilao).strip(" -")

    return f"{nome_leilao} - {data_contrato}", data_contrato


def extrair_comprador(texto):
    match = re.search(r"Comprador:\s*(.*?)\s*-\s*([\d\.\-\/]+)", texto)

    if not match:
        return "", ""

    return match.group(1).strip(), match.group(2).strip()


def extrair_vendedor(texto):
    match = re.search(r"Vendedor:\s*(.*?)\s*Comprador:", texto)
    return match.group(1).strip() if match else ""


def extrair_endereco(texto):
    match = re.search(r"Endere[cç]o:\s*(.*?)\s*E-mail:", texto)
    return match.group(1).strip() if match else ""


def extrair_parcelas(texto):
    parcelas = []
    padrao_parcelas = re.findall(
        r"(\d{2})/\s*(\d{2})\s*-\s*(\d{2}/\d{2}/\d{4})\s*-\s*R\$\s*([\d\.,]+)",
        texto,
    )

    for parcela in padrao_parcelas:
        parcelas.append(
            {
                "parcela": int(parcela[0]),
                "vencimento": parcela[2],
                "valor": float(parcela[3].replace(".", "").replace(",", ".")),
            }
        )

    return parcelas


def tratar_endereco(endereco):
    numero = ""
    cep = ""
    cidade = ""
    uf = ""
    bairro = BAIRRO_PADRAO
    complemento = ""
    logradouro = ""
    partes = [parte.strip() for parte in endereco.split(" - ") if parte.strip()]

    for parte in partes:
        match_cep = re.search(r"\d{5}-\d{3}", parte)

        if match_cep:
            cep = match_cep.group()
            break

    for indice in range(len(partes) - 1, -1, -1):
        match_uf = re.search(r"\b([A-Z]{2})\b", partes[indice])

        if match_uf:
            uf = match_uf.group()

            if indice > 0:
                cidade = partes[indice - 1].strip()

            break

    if partes:
        match_logradouro = re.search(r"(.*?),\s*([\d]+|S/N)", partes[0], re.IGNORECASE)

        if match_logradouro:
            logradouro = match_logradouro.group(1).strip()
            numero = match_logradouro.group(2).upper()
        else:
            logradouro = partes[0]

    candidatos = selecionar_candidatos_bairro(partes, cidade, uf)
    possiveis_bairro = []
    possiveis_complemento = []

    for candidato in candidatos:
        if eh_complemento_endereco(candidato):
            possiveis_complemento.append(candidato)
        elif not deve_ignorar_bairro(candidato):
            possiveis_bairro.append(candidato)

    if possiveis_bairro:
        bairro = possiveis_bairro[-1]

    if possiveis_complemento:
        complemento = " - ".join(possiveis_complemento)

    return logradouro, numero, cep, cidade, uf, bairro, complemento


def selecionar_candidatos_bairro(partes, cidade, uf):
    ignorar = {"KM", "CAIXA POSTAL", "CEP", "METROS"}
    candidatos = []

    for parte in partes:
        texto_normalizado = normalizar_texto(parte)

        if any(item in texto_normalizado for item in ignorar):
            continue

        if parte in {cidade, uf} or parte == partes[0]:
            continue

        candidatos.append(parte)

    return candidatos


def normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return texto.upper()


def eh_complemento_endereco(texto):
    texto_normalizado = normalizar_texto(texto)
    return any(palavra in texto_normalizado for palavra in PALAVRAS_COMPLEMENTO)


def deve_ignorar_bairro(texto):
    texto_normalizado = normalizar_texto(texto)
    return any(palavra in texto_normalizado for palavra in PALAVRAS_IGNORAR_BAIRRO)


def gerar_planilha_cadastro_mapa(paginas):
    linhas = montar_linhas_exportacao(paginas)
    arquivo = BytesIO()

    with ZipFile(arquivo, "w", ZIP_DEFLATED) as planilha:
        planilha.writestr("[Content_Types].xml", conteudo_tipos())
        planilha.writestr("_rels/.rels", relacoes_raiz())
        planilha.writestr("docProps/core.xml", propriedades_core())
        planilha.writestr("docProps/app.xml", propriedades_app())
        planilha.writestr("xl/workbook.xml", workbook_xml())
        planilha.writestr("xl/_rels/workbook.xml.rels", workbook_rels())
        planilha.writestr("xl/styles.xml", styles_xml())
        planilha.writestr("xl/worksheets/sheet1.xml", worksheet_xml(linhas))

    arquivo.seek(0)
    return arquivo


def montar_linhas_exportacao(paginas):
    linhas = [[titulo for _, titulo in COLUNAS_EXPORTACAO]]

    for pagina in paginas:
        telefones = pagina.get("telefones") or []
        emails = pagina.get("emails") or []

        dados_base = {
            "leilao": pagina.get("leilao", ""),
            "datacontrato": pagina.get("datacontrato", ""),
            "produto": pagina.get("produto", ""),
            "vendedor": pagina.get("vendedor", ""),
            "comprador": pagina.get("comprador", ""),
            "cpfcnpj": pagina.get("cpfcnpj", ""),
            "endereco": pagina.get("endereco", ""),
            "numero": pagina.get("numero", ""),
            "bairro": pagina.get("bairro", ""),
            "cep": pagina.get("cep", ""),
            "cidade": pagina.get("cidade", ""),
            "uf": pagina.get("uf", ""),
            "complemento": pagina.get("complemento", ""),
            "telefone1": obter_item(telefones, 0),
            "telefone2": obter_item(telefones, 1),
            "telefone3": obter_item(telefones, 2),
            "email1": obter_item(emails, 0),
            "email2": obter_item(emails, 1),
            "email3": obter_item(emails, 2),
            "observacao": pagina.get("observacao", ""),
        }

        for parcela in pagina.get("parcelas") or []:
            linha = {
                **dados_base,
                "parcela": parcela.get("parcela", ""),
                "vencimento": parcela.get("vencimento", ""),
                "valor": parcela.get("valor", 0),
            }
            linhas.append([linha.get(chave, "") for chave, _ in COLUNAS_EXPORTACAO])

    return linhas


def obter_item(lista, indice):
    return lista[indice] if len(lista) > indice else ""


def worksheet_xml(linhas):
    linhas_xml = []

    for indice_linha, linha in enumerate(linhas, start=1):
        celulas_xml = []

        for indice_coluna, valor in enumerate(linha, start=1):
            referencia = f"{nome_coluna(indice_coluna)}{indice_linha}"
            estilo = "1" if indice_linha == 1 else ("2" if referencia.startswith("W") else "0")
            celulas_xml.append(celula_xml(referencia, valor, estilo))

        linhas_xml.append(f'<row r="{indice_linha}">{"".join(celulas_xml)}</row>')

    dimensao = f"A1:{nome_coluna(len(COLUNAS_EXPORTACAO))}{max(len(linhas), 1)}"
    colunas = "".join(
        f'<col min="{indice}" max="{indice}" width="{largura}" customWidth="1"/>'
        for indice, largura in enumerate(larguras_colunas(), start=1)
    )

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <dimension ref="{dimensao}"/>
    <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
    <cols>{colunas}</cols>
    <sheetData>{"".join(linhas_xml)}</sheetData>
</worksheet>'''


def celula_xml(referencia, valor, estilo):
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return f'<c r="{referencia}" s="{estilo}"><v>{valor}</v></c>'

    texto = escape(str(valor or ""))
    return f'<c r="{referencia}" s="{estilo}" t="inlineStr"><is><t>{texto}</t></is></c>'


def nome_coluna(indice):
    nome = ""

    while indice:
        indice, resto = divmod(indice - 1, 26)
        nome = chr(65 + resto) + nome

    return nome


def larguras_colunas():
    return [
        32,
        14,
        14,
        28,
        28,
        18,
        34,
        10,
        18,
        12,
        20,
        8,
        22,
        18,
        18,
        18,
        28,
        28,
        28,
        42,
        16,
        14,
        14,
    ]


def conteudo_tipos():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
    <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''


def relacoes_raiz():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
    <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def workbook_xml():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets><sheet name="Clientes" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''


def workbook_rels():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''


def styles_xml():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <fonts count="2">
        <font><sz val="11"/><name val="Calibri"/></font>
        <font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font>
    </fonts>
    <fills count="3">
        <fill><patternFill patternType="none"/></fill>
        <fill><patternFill patternType="gray125"/></fill>
        <fill><patternFill patternType="solid"><fgColor rgb="FF176B87"/><bgColor indexed="64"/></patternFill></fill>
    </fills>
    <borders count="2">
        <border><left/><right/><top/><bottom/><diagonal/></border>
        <border>
            <left style="thin"><color rgb="FFD9E2E8"/></left>
            <right style="thin"><color rgb="FFD9E2E8"/></right>
            <top style="thin"><color rgb="FFD9E2E8"/></top>
            <bottom style="thin"><color rgb="FFD9E2E8"/></bottom>
            <diagonal/>
        </border>
    </borders>
    <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
    <cellXfs count="3">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"/>
        <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFill="1" applyFont="1" applyAlignment="1">
            <alignment horizontal="center"/>
        </xf>
        <xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"/>
    </cellXfs>
</styleSheet>'''


def propriedades_core():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:dcterms="http://purl.org/dc/terms/"
    xmlns:dcmitype="http://purl.org/dc/dcmitype/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <dc:title>Clientes</dc:title>
    <dc:creator>Meu Painel Flask</dc:creator>
</cp:coreProperties>'''


def propriedades_app():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
    <Application>Meu Painel Flask</Application>
</Properties>'''
