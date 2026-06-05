from flask import url_for
from werkzeug.routing import BuildError

from apps.comum.extensoes import db
from apps.comum.modelos import Aplicacao, Usuario


def montar_aplicacoes_para_painel(usuario):
    return [
        {
            "nome": aplicativo.nome,
            "descricao": aplicativo.descricao,
            "icone": aplicativo.icone,
            "imagem_icone": aplicativo.imagem_icone,
            "cor": aplicativo.cor,
            "url": resolver_url_aplicacao(aplicativo),
        }
        for aplicativo in listar_aplicacoes_liberadas(usuario)
    ]


def listar_aplicacoes_liberadas(usuario):
    consulta = (
        db.select(Aplicacao)
        .where(Aplicacao.ativa.is_(True))
        .order_by(Aplicacao.ordem.asc(), Aplicacao.nome.asc())
    )

    if not usuario.tem_perfil_admin:
        consulta = consulta.join(Aplicacao.usuarios).where(
            Usuario.id == usuario.id,
            Aplicacao.endpoint.notlike("dashboard.%"),
        )

    return db.session.execute(consulta).scalars().all()


def resolver_url_aplicacao(aplicacao):
    if aplicacao.url_externa:
        return aplicacao.url_externa

    if aplicacao.endpoint:
        try:
            return url_for(aplicacao.endpoint)
        except BuildError:
            return "#"

    return "#"
