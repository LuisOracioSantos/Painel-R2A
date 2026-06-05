import hmac
from functools import wraps
from secrets import token_urlsafe

from flask import abort, redirect, request, session, url_for
from flask_login import current_user, login_required


CHAVE_CSRF_SESSAO = "_csrf_token"


def gerar_token_csrf():
    token = session.get(CHAVE_CSRF_SESSAO)

    if not token:
        token = token_urlsafe(32)
        session[CHAVE_CSRF_SESSAO] = token

    return token


def validar_token_csrf():
    token_sessao = session.get(CHAVE_CSRF_SESSAO)
    token_enviado = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")

    return bool(
        token_sessao
        and token_enviado
        and hmac.compare_digest(token_sessao, token_enviado)
    )


def registrar_protecao_csrf(app):
    @app.before_request
    def proteger_requisicoes_com_estado():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not validar_token_csrf():
            abort(400)


def acesso_admin_obrigatorio(funcao):
    @wraps(funcao)
    @login_required
    def funcao_protegida(*args, **kwargs):
        if not current_user.tem_perfil_admin:
            abort(403)

        return funcao(*args, **kwargs)

    return funcao_protegida


def acesso_aplicacao_obrigatorio(endpoint_aplicacao):
    def decorador(funcao):
        @wraps(funcao)
        @login_required
        def funcao_protegida(*args, **kwargs):
            if current_user.tem_perfil_admin or usuario_tem_acesso_aplicacao(endpoint_aplicacao):
                return funcao(*args, **kwargs)

            abort(403)

        return funcao_protegida

    return decorador


def usuario_tem_acesso_aplicacao(endpoint_aplicacao):
    return any(
        aplicacao.ativa and aplicacao.endpoint == endpoint_aplicacao
        for aplicacao in current_user.aplicacoes
    )


def destino_pos_login():
    proximo_destino = request.args.get("next")

    if (
        proximo_destino
        and proximo_destino.startswith("/")
        and not proximo_destino.startswith("//")
    ):
        return proximo_destino

    return url_for("painel_principal.exibir_painel")
