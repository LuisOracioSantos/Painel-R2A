import re
import unicodedata
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from apps.comum.extensoes import db
from apps.comum.modelos import Aplicacao, ConfiguracaoSistema, Usuario


CHAVE_LOGO_EMPRESA = "logo_empresa"
EXTENSOES_LOGO_PERMITIDAS = {"png", "jpg", "jpeg", "webp", "gif"}
EXTENSOES_ICONE_PERMITIDAS = {"png", "jpg", "jpeg", "webp", "gif"}


def listar_usuarios():
    return Usuario.query.order_by(Usuario.nome.asc()).all()


def listar_aplicacoes():
    return Aplicacao.query.order_by(Aplicacao.ordem.asc(), Aplicacao.nome.asc()).all()


def obter_logo_empresa():
    configuracao = ConfiguracaoSistema.query.filter_by(chave=CHAVE_LOGO_EMPRESA).first()
    return configuracao.valor if configuracao else None


def salvar_logo_empresa(arquivo):
    if not arquivo or not arquivo.filename:
        return False, "Selecione um arquivo de logo."

    extensao = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if extensao not in EXTENSOES_LOGO_PERMITIDAS:
        return False, "Use uma imagem PNG, JPG, WEBP ou GIF."

    nome_seguro = secure_filename(arquivo.filename) or f"logo.{extensao}"
    caminho_relativo = Path("uploads") / "empresa" / f"logo.{extensao}"
    caminho_destino = Path(current_app.static_folder) / caminho_relativo
    caminho_destino.parent.mkdir(parents=True, exist_ok=True)

    remover_arquivos_logo_existentes(caminho_destino)
    arquivo.save(caminho_destino)
    gravar_configuracao(CHAVE_LOGO_EMPRESA, caminho_relativo.as_posix())

    return True, f"Logo {nome_seguro} salvo com sucesso."


def remover_logo_empresa():
    caminho_logo = obter_logo_empresa()
    if caminho_logo:
        caminho_arquivo = Path(current_app.static_folder) / caminho_logo
        if caminho_arquivo.exists():
            caminho_arquivo.unlink()

    gravar_configuracao(CHAVE_LOGO_EMPRESA, None)
    return True, "Logo removido com sucesso."


def gravar_configuracao(chave, valor):
    configuracao = ConfiguracaoSistema.query.filter_by(chave=chave).first()

    if not configuracao:
        configuracao = ConfiguracaoSistema(chave=chave)
        db.session.add(configuracao)

    configuracao.valor = valor
    db.session.commit()


def remover_arquivos_logo_existentes(caminho_destino):
    for caminho in caminho_destino.parent.glob("logo.*"):
        if caminho != caminho_destino:
            caminho.unlink()


def salvar_icone_aplicacao(aplicacao_id, arquivo):
    if not arquivo or not arquivo.filename:
        return True, "", None

    extensao = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if extensao not in EXTENSOES_ICONE_PERMITIDAS:
        return False, "Use uma imagem PNG, JPG, WEBP ou GIF para o icone.", None

    secure_filename(arquivo.filename)
    caminho_relativo = Path("uploads") / "aplicacoes" / f"app-{aplicacao_id}.{extensao}"
    caminho_destino = Path(current_app.static_folder) / caminho_relativo
    caminho_destino.parent.mkdir(parents=True, exist_ok=True)

    for caminho in caminho_destino.parent.glob(f"app-{aplicacao_id}.*"):
        if caminho != caminho_destino:
            caminho.unlink()

    arquivo.save(caminho_destino)
    return True, "", caminho_relativo.as_posix()


def remover_arquivo_estatico(caminho_relativo):
    if not caminho_relativo:
        return

    caminho_arquivo = Path(current_app.static_folder) / caminho_relativo
    if caminho_arquivo.exists():
        caminho_arquivo.unlink()


def calcular_metricas(usuarios, aplicativos):
    return [
        {
            "rotulo": "Aplicações ativas",
            "valor": sum(1 for aplicativo in aplicativos if aplicativo.ativa),
        },
        {"rotulo": "Usuários ativos", "valor": sum(1 for usuario in usuarios if usuario.ativo)},
        {"rotulo": "Perfis admin", "valor": sum(1 for usuario in usuarios if usuario.tem_perfil_admin)},
    ]


def criar_aplicacao_por_formulario(formulario, arquivos=None):
    nome = formulario.get("nome", "").strip()
    descricao = formulario.get("descricao", "").strip()
    endpoint = formulario.get("endpoint", "").strip() or None
    url_externa = formulario.get("url_externa", "").strip() or None
    icone = formulario.get("icone", "APP").strip().upper()[:8] or "APP"
    cor = normalizar_cor(formulario.get("cor", "#176b87"))
    ordem = converter_inteiro(formulario.get("ordem"), padrao=100)

    if not nome:
        return False, "Informe o nome da aplicação."

    if not endpoint and not url_externa:
        return False, "Informe um endpoint interno ou uma URL externa."

    aplicacao = Aplicacao(
        nome=nome,
        slug=gerar_slug_unico(nome),
        descricao=descricao,
        endpoint=endpoint,
        url_externa=url_externa,
        icone=icone,
        cor=cor,
        ordem=ordem,
        ativa=formulario.get("ativa") == "on",
    )
    db.session.add(aplicacao)
    db.session.flush()

    sucesso, mensagem, caminho_icone = salvar_icone_aplicacao(
        aplicacao.id,
        arquivos.get("imagem_icone") if arquivos else None,
    )
    if not sucesso:
        db.session.rollback()
        return False, mensagem

    aplicacao.imagem_icone = caminho_icone
    db.session.commit()

    return True, "Aplicação criada com sucesso."


def atualizar_aplicacao_por_formulario(aplicacao_id, formulario, arquivos=None):
    aplicacao = db.get_or_404(Aplicacao, aplicacao_id)
    nome = formulario.get("nome", "").strip()
    descricao = formulario.get("descricao", "").strip()
    endpoint = formulario.get("endpoint", "").strip() or None
    url_externa = formulario.get("url_externa", "").strip() or None
    icone = formulario.get("icone", "APP").strip().upper()[:8] or "APP"
    cor = normalizar_cor(formulario.get("cor", "#176b87"))
    ordem = converter_inteiro(formulario.get("ordem"), padrao=100)

    if not nome:
        return False, "Informe o nome da aplicacao."

    if not endpoint and not url_externa:
        return False, "Informe um endpoint interno ou uma URL externa."

    aplicacao.nome = nome
    aplicacao.descricao = descricao
    aplicacao.endpoint = endpoint
    aplicacao.url_externa = url_externa
    aplicacao.icone = icone
    aplicacao.cor = cor
    aplicacao.ordem = ordem
    aplicacao.ativa = formulario.get("ativa") == "on"

    sucesso, mensagem, caminho_icone = salvar_icone_aplicacao(
        aplicacao.id,
        arquivos.get("imagem_icone") if arquivos else None,
    )
    if not sucesso:
        return False, mensagem

    if caminho_icone:
        remover_arquivo_estatico(aplicacao.imagem_icone)
        aplicacao.imagem_icone = caminho_icone

    db.session.commit()
    return True, "Aplicacao atualizada com sucesso."


def remover_icone_aplicacao(aplicacao_id):
    aplicacao = db.get_or_404(Aplicacao, aplicacao_id)
    remover_arquivo_estatico(aplicacao.imagem_icone)
    aplicacao.imagem_icone = None
    db.session.commit()
    return True, "Imagem da aplicacao removida com sucesso."


def alternar_status_aplicacao(aplicacao_id):
    aplicacao = db.get_or_404(Aplicacao, aplicacao_id)
    aplicacao.ativa = not aplicacao.ativa
    db.session.commit()


def excluir_aplicacao(aplicacao_id):
    aplicacao = db.get_or_404(Aplicacao, aplicacao_id)
    nome = aplicacao.nome

    aplicacao.usuarios.clear()
    remover_arquivo_estatico(aplicacao.imagem_icone)
    db.session.delete(aplicacao)
    db.session.commit()

    return True, f"Aplicacao {nome} excluida com sucesso."


def criar_usuario_por_formulario(formulario):
    nome = formulario.get("nome", "").strip()
    email = formulario.get("email", "").strip().lower()
    senha = formulario.get("senha", "")
    perfil = "admin" if formulario.get("perfil") == "admin" else "usuario"
    id_cadastro, erro_id_cadastro = validar_id_cadastro(formulario.get("id_cadastro"))

    if not nome or not email or not senha:
        return False, "Preencha nome, e-mail e senha."

    if erro_id_cadastro:
        return False, erro_id_cadastro

    if len(senha) < 8:
        return False, "A senha precisa ter pelo menos 8 caracteres."

    usuario_existente = Usuario.query.filter_by(email=email).first()

    if usuario_existente:
        return False, "Já existe um usuário com esse e-mail."

    if id_cadastro_em_uso(id_cadastro):
        return False, "Esse Id de cadastro ja esta em uso por outro usuario."

    usuario = Usuario(nome=nome, email=email, perfil=perfil, id_cadastro=id_cadastro, ativo=True)
    usuario.definir_senha(senha)
    db.session.add(usuario)
    db.session.commit()

    return True, "Usuário criado com sucesso."


def atualizar_usuario_por_formulario(usuario_id, formulario):
    usuario = db.get_or_404(Usuario, usuario_id)
    nome = formulario.get("nome", "").strip()
    email = formulario.get("email", "").strip().lower()
    perfil = "admin" if formulario.get("perfil") == "admin" else "usuario"
    id_cadastro, erro_id_cadastro = validar_id_cadastro(formulario.get("id_cadastro"))

    if not nome or not email:
        return False, "Preencha nome e e-mail."

    if erro_id_cadastro:
        return False, erro_id_cadastro

    usuario_existente = Usuario.query.filter(Usuario.email == email, Usuario.id != usuario.id).first()
    if usuario_existente:
        return False, "Já existe outro usuário com esse e-mail."

    if id_cadastro_em_uso(id_cadastro, usuario_id_ignorado=usuario.id):
        return False, "Esse Id de cadastro ja esta em uso por outro usuario."

    usuario.nome = nome
    usuario.email = email
    usuario.perfil = perfil
    usuario.id_cadastro = id_cadastro
    db.session.commit()

    return True, "Usuário atualizado com sucesso."


def alternar_status_usuario(usuario_id, usuario_atual_id):
    usuario = db.get_or_404(Usuario, usuario_id)

    if usuario.id == usuario_atual_id:
        return False, "Você não pode inativar o próprio usuário."

    usuario.ativo = not usuario.ativo
    db.session.commit()

    return True, "Status do usuário atualizado."


def atualizar_acessos_por_formulario(formulario):
    usuario = db.get_or_404(Usuario, converter_inteiro(formulario.get("usuario_id")))
    aplicacoes_ids = [
        converter_inteiro(aplicacao_id)
        for aplicacao_id in formulario.getlist("aplicacoes_ids")
    ]
    aplicacoes_ids = [aplicacao_id for aplicacao_id in aplicacoes_ids if aplicacao_id]
    aplicacoes = Aplicacao.query.filter(Aplicacao.id.in_(aplicacoes_ids)).all()
    usuario.aplicacoes = aplicacoes
    db.session.commit()


def gerar_slug_unico(nome):
    slug_base = normalizar_slug(nome)
    slug = slug_base
    contador = 2

    while Aplicacao.query.filter_by(slug=slug).first():
        slug = f"{slug_base}-{contador}"
        contador += 1

    return slug


def normalizar_slug(texto):
    texto_ascii = (
        unicodedata.normalize("NFKD", texto)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", texto_ascii).strip("-")
    return slug or "aplicacao"


def normalizar_cor(cor):
    cor = (cor or "").strip()

    if re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
        return cor

    return "#176b87"


def converter_inteiro(valor, padrao=None):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def validar_id_cadastro(valor):
    valor = str(valor or "").strip()
    if not valor:
        return None, None

    if not re.fullmatch(r"\d", valor):
        return None, "O Id de cadastro deve ser um numero de 0 a 9."

    return int(valor), None


def id_cadastro_em_uso(id_cadastro, usuario_id_ignorado=None):
    if id_cadastro is None:
        return False

    consulta = Usuario.query.filter_by(id_cadastro=id_cadastro)
    if usuario_id_ignorado is not None:
        consulta = consulta.filter(Usuario.id != usuario_id_ignorado)

    return consulta.first() is not None
