from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from apps.comum.seguranca import acesso_admin_obrigatorio
from apps.dashboard.servicos import (
    alternar_status_aplicacao as alternar_status_aplicacao_servico,
    alternar_status_usuario as alternar_status_usuario_servico,
    atualizar_acessos_por_formulario,
    atualizar_aplicacao_por_formulario,
    atualizar_usuario_por_formulario,
    calcular_metricas,
    criar_aplicacao_por_formulario,
    criar_usuario_por_formulario,
    excluir_aplicacao as excluir_aplicacao_servico,
    listar_aplicacoes,
    listar_usuarios,
    obter_logo_empresa,
    remover_icone_aplicacao,
    remover_logo_empresa,
    salvar_logo_empresa,
)


dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="static",
    url_prefix="/admin",
)


@dashboard_bp.get("/")
@acesso_admin_obrigatorio
def exibir_dashboard():
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.get("/aplicacoes")
@acesso_admin_obrigatorio
def exibir_catalogo_aplicacoes():
    aplicativos = listar_aplicacoes()

    return render_template(
        "dashboard/index.html",
        titulo_pagina="Catalogo de aplicacoes",
        secao_ativa="aplicacoes",
        aplicativos=aplicativos,
        logo_empresa=obter_logo_empresa(),
        metricas=[
            {"rotulo": "Aplicacoes cadastradas", "valor": len(aplicativos)},
            {
                "rotulo": "Aplicacoes ativas",
                "valor": sum(1 for aplicativo in aplicativos if aplicativo.ativa),
            },
            {
                "rotulo": "Aplicacoes inativas",
                "valor": sum(1 for aplicativo in aplicativos if not aplicativo.ativa),
            },
        ],
    )


@dashboard_bp.get("/contas-perfis")
@acesso_admin_obrigatorio
def exibir_contas_perfis():
    usuarios = listar_usuarios()

    return render_template(
        "dashboard/index.html",
        titulo_pagina="Contas e Perfis",
        secao_ativa="usuarios",
        usuarios=usuarios,
        metricas=[
            {"rotulo": "Usuarios cadastrados", "valor": len(usuarios)},
            {"rotulo": "Usuarios ativos", "valor": sum(1 for usuario in usuarios if usuario.ativo)},
            {"rotulo": "Perfis admin", "valor": sum(1 for usuario in usuarios if usuario.tem_perfil_admin)},
        ],
    )


@dashboard_bp.get("/acessos")
@acesso_admin_obrigatorio
def exibir_acessos_usuario():
    usuarios = listar_usuarios()
    aplicativos = listar_aplicacoes()

    return render_template(
        "dashboard/index.html",
        titulo_pagina="Acesso por Usuario",
        secao_ativa="acessos",
        aplicativos=aplicativos,
        metricas=calcular_metricas(usuarios, aplicativos),
        usuarios=usuarios,
    )


@dashboard_bp.post("/aplicacoes")
@acesso_admin_obrigatorio
def criar_aplicacao():
    sucesso, mensagem = criar_aplicacao_por_formulario(request.form, request.files)
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.post("/aplicacoes/<int:aplicacao_id>/editar")
@acesso_admin_obrigatorio
def editar_aplicacao(aplicacao_id):
    sucesso, mensagem = atualizar_aplicacao_por_formulario(aplicacao_id, request.form, request.files)
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.post("/aplicacoes/<int:aplicacao_id>/remover-icone")
@acesso_admin_obrigatorio
def remover_icone(aplicacao_id):
    sucesso, mensagem = remover_icone_aplicacao(aplicacao_id)
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.post("/aplicacoes/<int:aplicacao_id>/alternar-status")
@acesso_admin_obrigatorio
def alternar_status_aplicacao(aplicacao_id):
    alternar_status_aplicacao_servico(aplicacao_id)
    flash("Status da aplicacao atualizado.", "sucesso")
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.post("/aplicacoes/<int:aplicacao_id>/excluir")
@acesso_admin_obrigatorio
def excluir_aplicacao(aplicacao_id):
    sucesso, mensagem = excluir_aplicacao_servico(aplicacao_id)
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.post("/logo")
@acesso_admin_obrigatorio
def atualizar_logo_empresa():
    sucesso, mensagem = salvar_logo_empresa(request.files.get("logo_empresa"))
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.post("/logo/remover")
@acesso_admin_obrigatorio
def remover_logo():
    sucesso, mensagem = remover_logo_empresa()
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_catalogo_aplicacoes"))


@dashboard_bp.post("/usuarios")
@acesso_admin_obrigatorio
def criar_usuario():
    sucesso, mensagem = criar_usuario_por_formulario(request.form)
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_contas_perfis"))


@dashboard_bp.post("/usuarios/<int:usuario_id>/editar")
@acesso_admin_obrigatorio
def editar_usuario(usuario_id):
    sucesso, mensagem = atualizar_usuario_por_formulario(usuario_id, request.form)
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_contas_perfis"))


@dashboard_bp.post("/usuarios/<int:usuario_id>/alternar-status")
@acesso_admin_obrigatorio
def alternar_status_usuario(usuario_id):
    sucesso, mensagem = alternar_status_usuario_servico(usuario_id, current_user.id)
    flash(mensagem, "sucesso" if sucesso else "erro")
    return redirect(url_for("dashboard.exibir_contas_perfis"))


@dashboard_bp.post("/acessos")
@acesso_admin_obrigatorio
def atualizar_acessos_usuario():
    atualizar_acessos_por_formulario(request.form)
    flash("Acessos atualizados com sucesso.", "sucesso")
    return redirect(url_for("dashboard.exibir_acessos_usuario"))
