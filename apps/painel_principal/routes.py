from flask import Blueprint, render_template
from flask_login import current_user, login_required

from apps.painel_principal.servicos import montar_aplicacoes_para_painel


painel_principal_bp = Blueprint(
    "painel_principal",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/painel-principal/static",
)


@painel_principal_bp.get("/")
@painel_principal_bp.get("/painel")
@login_required
def exibir_painel():
    return render_template(
        "painel_principal/index.html",
        titulo_pagina="Painel Principal",
        aplicativos=montar_aplicacoes_para_painel(current_user),
    )
