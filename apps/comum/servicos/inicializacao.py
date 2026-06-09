from pathlib import Path

from flask import current_app
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from apps.comum.extensoes import db
from apps.comum.modelos import Aplicacao, Usuario


def inicializar_banco_de_dados(app):
    if not app.config["CRIAR_BANCO_AUTOMATICAMENTE"]:
        return

    caminho_banco = app.config["SQLALCHEMY_DATABASE_URI"]

    if caminho_banco.startswith("sqlite:///"):
        caminho_arquivo = Path(caminho_banco.replace("sqlite:///", "", 1))
        caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        db.create_all()
        aplicar_migracoes_simples()
        criar_dados_iniciais()


def aplicar_migracoes_simples():
    inspetor = inspect(db.engine)
    if "aplicacoes" not in inspetor.get_table_names():
        return

    colunas_aplicacoes = {coluna["name"] for coluna in inspetor.get_columns("aplicacoes")}
    if "imagem_icone" not in colunas_aplicacoes:
        db.session.execute(text("ALTER TABLE aplicacoes ADD COLUMN imagem_icone VARCHAR(500)"))
        db.session.commit()

    if "usuarios" in inspetor.get_table_names():
        colunas_usuarios = {coluna["name"] for coluna in inspetor.get_columns("usuarios")}
        if "id_cadastro" not in colunas_usuarios:
            db.session.execute(text("ALTER TABLE usuarios ADD COLUMN id_cadastro INTEGER"))
            db.session.commit()

        indices_usuarios = {indice["name"] for indice in inspetor.get_indexes("usuarios")}
        if "ix_usuarios_id_cadastro" not in indices_usuarios:
            db.session.execute(text("CREATE UNIQUE INDEX ix_usuarios_id_cadastro ON usuarios (id_cadastro)"))
            db.session.commit()


def criar_dados_iniciais():
    admin = obter_ou_criar_admin()
    aplicacoes = obter_ou_criar_aplicacoes_padrao()

    for aplicacao in aplicacoes:
        if aplicacao not in admin.aplicacoes:
            admin.aplicacoes.append(aplicacao)

    db.session.commit()


def obter_ou_criar_admin():
    email = current_app.config["ADMIN_PADRAO_EMAIL"].strip().lower()
    admin = Usuario.query.filter_by(email=email).first()

    if admin:
        return admin

    admin = Usuario(
        nome=current_app.config["ADMIN_PADRAO_NOME"],
        email=email,
        perfil="admin",
        ativo=True,
    )
    admin.definir_senha(current_app.config["ADMIN_PADRAO_SENHA"])
    db.session.add(admin)

    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return Usuario.query.filter_by(email=email).first()

    return admin


def obter_ou_criar_aplicacoes_padrao():
    painel = obter_ou_criar_aplicacao(
        nome="Painel Principal",
        slug="painel-principal",
        descricao="Acesso central as aplicacoes liberadas para o usuario.",
        endpoint="painel_principal.exibir_painel",
        icone="APP",
        cor="#176b87",
        ordem=10,
    )
    cadastro_mapa = obter_ou_criar_aplicacao(
        nome="Cadastro Mapa",
        slug="cadastro-mapa",
        descricao="Importe PDFs de mapa de compradores e revise os dados cadastrais.",
        endpoint="cadastromapa.exibir_cadastro_mapa",
        icone="MAP",
        cor="#2f8f7f",
        ordem=20,
    )
    cadastro_comissao = obter_ou_criar_aplicacao(
        nome="Cadastro Comissao",
        slug="cadastro-comissao",
        descricao="Importe PDFs de compradores e comissoes para gerar planilhas.",
        endpoint="cadastrocomissao.index",
        icone="COM",
        cor="#7a5c2e",
        ordem=30,
    )
    cadastro_boleto = obter_ou_criar_aplicacao(
        nome="Cadastro Boleto",
        slug="cadastro-boleto",
        descricao="Importe boletos e gere a planilha de legado para remessa.",
        endpoint="cadastroboleto.exibir_cadastro_boleto",
        icone="BOL",
        cor="#4f6f52",
        ordem=40,
    )
    configuracoes = obter_ou_criar_aplicacao(
        nome="Configuracoes",
        slug="configuracoes",
        descricao="Gerencie usuarios, aplicacoes, permissoes e disponibilidade.",
        endpoint="dashboard.exibir_catalogo_aplicacoes",
        icone="CFG",
        cor="#d9654f",
        ordem=90,
    )

    return [painel, cadastro_mapa, cadastro_comissao, cadastro_boleto, configuracoes]


def obter_ou_criar_aplicacao(**dados):
    aplicacao = Aplicacao.query.filter_by(slug=dados["slug"]).first()

    if aplicacao:
        return aplicacao

    aplicacao = Aplicacao(ativa=True, **dados)
    db.session.add(aplicacao)

    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return Aplicacao.query.filter_by(slug=dados["slug"]).first()

    return aplicacao
