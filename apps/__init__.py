from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, url_for

from apps.comum.extensoes import db, login_manager
from apps.comum.seguranca import gerar_token_csrf, registrar_protecao_csrf
from apps.comum.servicos.inicializacao import inicializar_banco_de_dados
from config import obter_configuracao


def criar_aplicacao(configuracao=None):
    """Cria e configura a instancia principal do Flask."""
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
        static_url_path="/static",
    )
    app.config.from_object(configuracao or obter_configuracao())

    registrar_extensoes(app)
    registrar_autenticacao(app)
    registrar_protecao_csrf(app)
    registrar_blueprints(app)
    registrar_contexto_template(app)
    registrar_tratadores_erro(app)
    registrar_comandos_cli(app)
    inicializar_banco_de_dados(app)

    return app


def registrar_extensoes(app):
    """Inicializa extensoes compartilhadas."""
    db.init_app(app)


def registrar_autenticacao(app):
    """Configura carregamento de usuarios e fluxo de login."""
    from apps.comum.modelos import Usuario

    login_manager.login_view = "autenticacao.exibir_login"
    login_manager.login_message = "Faça login para continuar."
    login_manager.login_message_category = "alerta"
    login_manager.init_app(app)

    @login_manager.user_loader
    def carregar_usuario(usuario_id):
        if not usuario_id.isdigit():
            return None

        return db.session.get(Usuario, int(usuario_id))

    @login_manager.unauthorized_handler
    def redirecionar_usuario_nao_autenticado():
        flash("Faça login para continuar.", "alerta")
        return redirect(url_for("autenticacao.exibir_login", next=request.full_path))


def registrar_blueprints(app):
    """Registra os blueprints das sub-aplicacoes."""
    from apps.autenticacao.routes import autenticacao_bp
    from apps.cadastroboleto.routes import cadastroboleto_bp
    from apps.cadastrocomissao.config import Config as ConfiguracaoCadastroComissao
    from apps.cadastrocomissao.routes import cadastrocomissao_bp
    from apps.cadastromapa.routes import cadastromapa_bp
    from apps.comum import comum_bp
    from apps.dashboard.routes import dashboard_bp
    from apps.painel_principal.routes import painel_principal_bp

    app.config.setdefault("ALLOWED_EXTENSIONS", ConfiguracaoCadastroComissao.ALLOWED_EXTENSIONS)
    app.config.setdefault("UPLOAD_FOLDER", ConfiguracaoCadastroComissao.UPLOAD_FOLDER)
    app.config.setdefault("EXTRACTION_FOLDER", ConfiguracaoCadastroComissao.EXTRACTION_FOLDER)
    app.config.setdefault("EXPORT_FOLDER", ConfiguracaoCadastroComissao.EXPORT_FOLDER)
    ConfiguracaoCadastroComissao.init_app(app)

    app.register_blueprint(comum_bp)
    app.register_blueprint(autenticacao_bp)
    app.register_blueprint(cadastroboleto_bp)
    app.register_blueprint(cadastromapa_bp)
    app.register_blueprint(cadastrocomissao_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(painel_principal_bp)


def registrar_contexto_template(app):
    """Disponibiliza dados compartilhados para todos os templates."""

    @app.context_processor
    def injetar_variaveis_globais():
        logo_empresa = obter_logo_empresa_configurado()
        return {
            "ano_atual": datetime.now().year,
            "csrf_token": gerar_token_csrf,
            "logo_empresa_url": url_for("static", filename=logo_empresa) if logo_empresa else None,
            "nome_sistema": app.config["NOME_SISTEMA"],
        }


def obter_logo_empresa_configurado():
    from apps.comum.modelos import ConfiguracaoSistema
    from apps.dashboard.servicos import CHAVE_LOGO_EMPRESA

    configuracao = ConfiguracaoSistema.query.filter_by(chave=CHAVE_LOGO_EMPRESA).first()
    return configuracao.valor if configuracao else None


def registrar_tratadores_erro(app):
    """Centraliza paginas de erro da aplicacao."""

    @app.errorhandler(404)
    def pagina_nao_encontrada(erro):
        return render_template("erros/404.html"), 404

    @app.errorhandler(403)
    def acesso_negado(erro):
        return render_template("erros/403.html"), 403

    @app.errorhandler(400)
    def requisicao_invalida(erro):
        return render_template("erros/400.html"), 400


def registrar_comandos_cli(app):
    """Registra comandos utilitarios para manutencao local."""

    @app.cli.command("inicializar-banco")
    def inicializar_banco():
        from apps.comum.servicos.inicializacao import criar_dados_iniciais

        db.create_all()
        criar_dados_iniciais()
        print("Banco inicializado com sucesso.")


__all__ = ["criar_aplicacao"]
