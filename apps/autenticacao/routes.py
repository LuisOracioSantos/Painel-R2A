from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from apps.autenticacao.servicos import validar_credenciais
from apps.comum.seguranca import destino_pos_login


autenticacao_bp = Blueprint(
    "autenticacao",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="static",
    url_prefix="/auth",
)


@autenticacao_bp.get("/login")
def exibir_login():
    if current_user.is_authenticated:
        return redirect(url_for("painel_principal.exibir_painel"))

    return render_template("autenticacao/login.html", titulo_pagina="Entrar")


@autenticacao_bp.post("/login")
def autenticar_usuario():
    email = request.form.get("email", "")
    senha = request.form.get("senha", "")
    lembrar = request.form.get("lembrar") == "on"
    usuario, erro = validar_credenciais(email, senha)

    if erro:
        flash(erro, "erro")
        return redirect(url_for("autenticacao.exibir_login"))

    login_user(usuario, remember=lembrar)
    return redirect(destino_pos_login())


@autenticacao_bp.post("/logout")
def encerrar_sessao():
    logout_user()
    flash("Sessão encerrada.", "sucesso")
    return redirect(url_for("autenticacao.exibir_login"))
