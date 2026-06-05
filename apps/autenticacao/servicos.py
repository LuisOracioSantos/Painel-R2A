from apps.comum.modelos import Usuario


def validar_credenciais(email, senha):
    usuario = Usuario.query.filter_by(email=email.strip().lower()).first()

    if not usuario or not usuario.verificar_senha(senha):
        return None, "E-mail ou senha inválidos."

    if not usuario.ativo:
        return None, "Usuário inativo. Fale com um administrador."

    return usuario, None
