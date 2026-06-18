import re
import unicodedata
from datetime import datetime
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
    ("cpfcnpj", "CPF/CNPJ"),
    ("comprador", "NOME / RAZÃO SOCIAL"),
    ("filial", "FILIAL"),
    ("numerocontrato", "NÚMERO CONTRATO"),
    ("datacontrato", "DATA CONTRATO"),
    ("plano", "PLANO"),
    ("tipoproduto", "TIPO DE PRODUTO"),
    ("observacaocontrato", "OBSERVAÇÃO  CONTRATO"),
    ("parcela", "PARCELA"),
    ("vencimento", "VENCIMENTO"),
    ("valor", "VALOR"),
    ("observacaoparcela", "OBSERVAÇÃO PARCELA"),
    ("telresidencial1", "TEL. RESIDENCIAL 1"),
    ("telresidencial2", "TEL. RESIDENCIAL 2"),
    ("telcomercial1", "TEL. COMERCIAL 1"),
    ("telcomercial2", "TEL. COMERCIAL 2"),
    ("telcelular1", "TEL. CELULAR 1"),
    ("telcelular2", "TEL. CELULAR 2"),
    ("telreferencia1", "TEL. REFERÊNCIA 1"),
    ("obstelreferencia1", "OBS.  TEL. REFERÊNCIA 1"),
    ("telreferencia2", "TEL. REFERÊNCIA 2"),
    ("obstelreferencia2", "OBS.  TEL. REFERÊNCIA 2"),
    ("telreferencia3", "TEL. REFERÊNCIA 3"),
    ("obstelreferencia3", "OBS.  TEL. REFERÊNCIA 3"),
    ("email1", "EMAIL 1"),
    ("email2", "EMAIL 2"),
    ("email3", "EMAIL 3"),
    ("enderecores", "ENDEREÇO RES."),
    ("numerores", "NUMERO RES."),
    ("complementores", "COMPLEMENTO RES."),
    ("bairrores", "BAIRRO RES."),
    ("cepres", "CEP  RES."),
    ("cidaderes", "CIDADE RES."),
    ("ufres", "UF RES."),
    ("enderecocom", "ENDEREÇO COM."),
    ("numerocom", "NUMERO COM."),
    ("complementocom", "COMPLEMENTO COM."),
    ("bairrocom", "BAIRRO COM."),
    ("cepcom", "CEP  COM."),
    ("cidadecom", "CIDADE COM."),
    ("ufcom", "UF COM."),
    ("rgie", "RG/IE"),
    ("datanasc", "DATA NASC."),
    ("pai", "PAI"),
    ("mae", "MAE"),
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
        extrair_dados_pagina(indice + 1, pagina.get_text())
        for indice, pagina in enumerate(documento_pdf)
    ]

    return {
        "total_paginas": len(paginas),
        "paginas": paginas,
    }


def extrair_dados_pagina(numero_pagina, texto):
    texto_normalizado = normalizar_espacos(texto)
    leilao, data_contrato = extrair_leilao(texto_normalizado)
    comprador, cpf_cnpj = extrair_comprador(texto_normalizado)
    vendedor = extrair_vendedor(texto_normalizado)
    endereco = extrair_endereco(texto_normalizado)
    logradouro, numero, cep, cidade, uf, bairro, complemento = tratar_endereco(endereco)
    telefones = re.findall(r"\(\d{2}\)\s*\d{4,5}-?\d+", texto_normalizado)
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", texto_normalizado)
    lotes_animais = extrair_lotes_animais(texto)

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
        "observacao": montar_observacao(leilao, lotes_animais),
        "parcelas": extrair_parcelas(texto_normalizado),
    }


def normalizar_espacos(texto):
    return re.sub(r"\s+", " ", texto or "")


def extrair_leilao(texto):
    match = re.search(
        r"(.*?)\s*-\s*(\d{2}/\d{2}/\d{4})\s*Cadastro de Compradores",
        texto,
    )

    if match:
        nome_leilao = match.group(1).strip()
        data_contrato = match.group(2)
    else:
        dados_leilao = extrair_leilao_entre_vendedor_e_comprador(texto)

        if not dados_leilao:
            return "", ""

        nome_leilao, data_contrato = dados_leilao

    nome_leilao = re.sub(r"\bNelore\b", "__NELORE__", nome_leilao, flags=re.IGNORECASE)

    for palavra in ["Leilao", "Leilão", "Virtual", "Nelore"]:
        nome_leilao = re.sub(rf"\b{palavra}\b", "", nome_leilao, flags=re.IGNORECASE)

    nome_leilao = nome_leilao.replace("__NELORE__", "Nelore")
    nome_leilao = re.sub(r"\s{2,}", " ", nome_leilao)
    nome_leilao = re.sub(r"\s*-\s*", " - ", nome_leilao).strip(" -")

    return f"{nome_leilao} - {data_contrato}", data_contrato


def extrair_leilao_entre_vendedor_e_comprador(texto):
    trecho_match = re.search(r"Vendedor:\s*(.*?)\s*Comprador:", texto)

    if not trecho_match:
        return None

    trecho = trecho_match.group(1)
    data_match = re.search(r"\d{2}/\d{2}/\d{4}", trecho)

    if not data_match:
        return None

    inicio_leilao = encontrar_inicio_leilao(trecho[: data_match.start()])

    if inicio_leilao is None:
        return None

    nome_leilao = trecho[inicio_leilao : data_match.start()].strip(" -")
    return nome_leilao, data_match.group()


def encontrar_inicio_leilao(texto):
    posicoes = []

    for padrao in [r"Leil[aã]o", "Virtual", "Nelore"]:
        for match in re.finditer(rf"\b{padrao}\b", texto, flags=re.IGNORECASE):
            posicoes.append(match.start())

    return max(posicoes) if posicoes else None


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


def extrair_lotes_animais(texto):
    itens_por_linhas = extrair_lotes_animais_por_linhas(texto)

    if itens_por_linhas:
        return itens_por_linhas

    itens = []
    texto_normalizado = normalizar_espacos(texto)
    padrao = re.compile(
        r"\b(?P<lote>\d{1,5})\s+"
        r"(?P<qtde>\d+)\s+"
        r"(?P<sexo>[A-Z])\s+"
        r"(?P<animal>.+?)\s+"
        r"(?P<peso>\d+(?:[,.]\d+)?)\s+"
        r"(?P<preco>\d{1,3}(?:\.\d{3})*,\d{2})\b"
    )

    for match in padrao.finditer(texto_normalizado):
        animal = formatar_descricao_animal(match.group("animal"))
        itens.append({"lote": match.group("lote"), "animal": animal})

    if itens:
        return itens

    return [{"lote": lote, "animal": ""} for lote in re.findall(r"\b(\d{1,5})\s+[A-Z]\b", texto_normalizado)]


def extrair_lotes_animais_por_linhas(texto):
    linhas = [linha.strip() for linha in str(texto or "").splitlines() if linha.strip()]

    for indice, linha in enumerate(linhas):
        if linha != "Qtde":
            continue

        if linhas[indice : indice + 4] != ["Qtde", "Lote", "Sexo", "Animal"]:
            continue

        try:
            inicio_valores = linhas.index("R$/KG", indice) + 1
        except ValueError:
            continue

        itens = extrair_itens_tabela(linhas[inicio_valores:])

        if itens:
            return itens

    return []


def extrair_itens_tabela(linhas):
    itens = []
    indice = 0

    while indice < len(linhas):
        item, proximo_indice = extrair_item_tabela(linhas, indice)

        if item:
            itens.append(item)
            indice = proximo_indice
        else:
            indice += 1

    return itens


def extrair_item_tabela(linhas, indice):
    if not re.fullmatch(r"\d+", linhas[indice]):
        return None, indice

    indice_lote = indice + 1
    lote_partes = []

    while indice_lote < len(linhas) and not eh_sexo_animal(linhas[indice_lote]):
        linha = linhas[indice_lote]

        if deve_parar_lote(linha) or len(lote_partes) >= 4:
            return None, indice

        lote_partes.append(linha)
        indice_lote += 1

    if not lote_partes or indice_lote >= len(linhas):
        return None, indice

    indice_animal = indice_lote + 1
    animal_linhas = coletar_linhas_animal(linhas[indice_animal:])

    if not animal_linhas:
        return None, indice

    lote = formatar_lote(lote_partes)
    animal = formatar_descricao_animal(" ".join(animal_linhas))

    return {"lote": lote, "animal": animal}, indice_animal + len(animal_linhas)


def eh_sexo_animal(linha):
    return normalizar_texto(linha) in {"M", "F", "S"}


def deve_parar_lote(linha):
    texto = normalizar_texto(linha)
    return (
        eh_inicio_condicao_pagamento(linha)
        or linha.startswith("R$")
        or texto in {"MACHOS", "FEMEAS", "TOTAL CRIAS", "SEM SEXO", "TOTAL DE ANIMAIS + CRIAS"}
        or bool(re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{2}", linha))
    )


def formatar_lote(partes):
    partes = [parte.strip() for parte in partes if parte.strip()]

    if all(re.fullmatch(r"[A-Za-z0-9]+", parte) for parte in partes):
        return "".join(partes)

    return " ".join(partes)


def coletar_linhas_animal(linhas):
    animal_linhas = []

    for linha in linhas:
        if eh_inicio_condicao_pagamento(linha):
            break

        if linha in {"Machos", "Fêmeas", "Femeas", "Sem sexo", "Total Crias"}:
            break

        animal_linhas.append(linha)

    return animal_linhas


def eh_inicio_condicao_pagamento(linha):
    texto = normalizar_texto(linha)
    return bool(
        re.search(r"\b\d+\+\d+\s+PARCELAS\b", texto)
        or re.search(r"\b\d+\s+PARCELAS\b", texto)
        or texto in {"MENSAL", "A VISTA", "AVISTA"}
    )


def formatar_descricao_animal(texto):
    texto = normalizar_espacos(texto).strip()
    return re.sub(r"^(\([^)]*%\))\s+", r"\1  ", texto)


def montar_observacao(leilao, lotes_animais):
    if not lotes_animais:
        return f"{leilao} - Lote(s): "

    if len(lotes_animais) == 1:
        item = lotes_animais[0]
        animal = f" - {item['animal']}" if item.get("animal") else ""
        return f"{leilao} - Lote: {item['lote']}{animal}"

    descricoes = []

    for item in lotes_animais:
        animal = f" - {item['animal']}" if item.get("animal") else ""
        descricoes.append(f"Lote: {item['lote']}{animal}")

    return f"{leilao} - {'; '.join(descricoes)}"


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


def gerar_planilha_cadastro_mapa(paginas, id_cadastro=None):
    linhas = montar_linhas_exportacao(paginas, id_cadastro=id_cadastro)
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


def montar_linhas_exportacao(paginas, id_cadastro=None):
    linhas = [[titulo for _, titulo in COLUNAS_EXPORTACAO]]
    id_cadastro = normalizar_id_cadastro(id_cadastro)

    for indice_pagina, pagina in enumerate(paginas, start=1):
        telefones = pagina.get("telefones") or []
        emails = pagina.get("emails") or []

        dados_base = {
            "cpfcnpj": pagina.get("cpfcnpj", ""),
            "comprador": pagina.get("comprador", ""),
            "filial": "",
            "numerocontrato": montar_numero_contrato(pagina, indice_pagina, id_cadastro),
            "datacontrato": pagina.get("datacontrato", ""),
            "plano": "",
            "tipoproduto": pagina.get("produto", ""),
            "observacaocontrato": pagina.get("observacao", ""),
            "observacaoparcela": "",
            "telresidencial1": formatar_telefone_exportacao(obter_item(telefones, 0)),
            "telresidencial2": formatar_telefone_exportacao(obter_item(telefones, 1)),
            "telcomercial1": "",
            "telcomercial2": "",
            "telcelular1": formatar_telefone_exportacao(obter_item(telefones, 2)),
            "telcelular2": "",
            "telreferencia1": "",
            "obstelreferencia1": "",
            "telreferencia2": "",
            "obstelreferencia2": "",
            "telreferencia3": "",
            "obstelreferencia3": "",
            "email1": obter_item(emails, 0),
            "email2": obter_item(emails, 1),
            "email3": obter_item(emails, 2),
            "enderecores": pagina.get("endereco", ""),
            "numerores": pagina.get("numero", ""),
            "complementores": pagina.get("complemento", ""),
            "bairrores": pagina.get("bairro", ""),
            "cepres": somente_digitos(pagina.get("cep", "")),
            "cidaderes": pagina.get("cidade", ""),
            "ufres": pagina.get("uf", ""),
            "enderecocom": "",
            "numerocom": "",
            "complementocom": "",
            "bairrocom": "",
            "cepcom": "",
            "cidadecom": "",
            "ufcom": "",
            "rgie": "",
            "datanasc": "",
            "pai": "",
            "mae": "",
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


def montar_numero_contrato(pagina, indice_pagina, id_cadastro):
    leilao = str(pagina.get("leilao", "") or "").strip()
    data_atual = datetime.now().strftime("%d%m%y")
    return f"{id_cadastro}{data_atual}{indice_pagina:03d}_{leilao or 'CADASTRO-MAPA'}"


def normalizar_id_cadastro(valor):
    valor = str(valor or "").strip()
    return valor if re.fullmatch(r"\d", valor) else "9"


def somente_digitos(valor):
    return re.sub(r"\D+", "", str(valor or ""))


def formatar_telefone_exportacao(valor):
    return re.sub(r"^\s*\((\d{2})\)\s*", r"\1", str(valor or ""))


def obter_item(lista, indice):
    return lista[indice] if len(lista) > indice else ""


def worksheet_xml(linhas):
    linhas_xml = []

    for indice_linha, linha in enumerate(linhas, start=1):
        celulas_xml = []

        for indice_coluna, valor in enumerate(linha, start=1):
            referencia = f"{nome_coluna(indice_coluna)}{indice_linha}"
            estilo = "1" if indice_linha == 1 else ("2" if indice_coluna == 11 else "0")
            celulas_xml.append(celula_xml(referencia, valor, estilo))

        linhas_xml.append(f'<row r="{indice_linha}">{"".join(celulas_xml)}</row>')

    dimensao = f"A1:{nome_coluna(len(COLUNAS_EXPORTACAO))}{max(len(linhas), 1)}"

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <dimension ref="{dimensao}"/>
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
        <font><b/><sz val="11"/><name val="Calibri"/></font>
    </fonts>
    <fills count="2">
        <fill><patternFill patternType="none"/></fill>
        <fill><patternFill patternType="gray125"/></fill>
    </fills>
    <borders count="1">
        <border><left/><right/><top/><bottom/><diagonal/></border>
    </borders>
    <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
    <cellXfs count="3">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
        <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
        <xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
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
