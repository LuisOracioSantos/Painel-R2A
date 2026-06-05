from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from apps.comum.extensoes import db


usuarios_aplicacoes = db.Table(
    "usuarios_aplicacoes",
    db.Column(
        "usuario_id",
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "aplicacao_id",
        db.Integer,
        db.ForeignKey("aplicacoes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column("criado_em", db.DateTime, default=datetime.utcnow, nullable=False),
)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(30), nullable=False, default="usuario", index=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    aplicacoes = db.relationship(
        "Aplicacao",
        secondary=usuarios_aplicacoes,
        back_populates="usuarios",
        lazy="selectin",
    )

    @property
    def is_active(self):
        return self.ativo

    @property
    def tem_perfil_admin(self):
        return self.perfil == "admin"

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


class Aplicacao(db.Model):
    __tablename__ = "aplicacoes"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(140), nullable=False, unique=True, index=True)
    descricao = db.Column(db.String(255), nullable=True)
    endpoint = db.Column(db.String(140), nullable=True)
    url_externa = db.Column(db.String(500), nullable=True)
    icone = db.Column(db.String(16), nullable=False, default="APP")
    imagem_icone = db.Column(db.String(500), nullable=True)
    cor = db.Column(db.String(20), nullable=False, default="#176b87")
    ativa = db.Column(db.Boolean, nullable=False, default=True, index=True)
    ordem = db.Column(db.Integer, nullable=False, default=100, index=True)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    atualizada_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    usuarios = db.relationship(
        "Usuario",
        secondary=usuarios_aplicacoes,
        back_populates="aplicacoes",
        lazy="selectin",
    )

    @property
    def destino_configurado(self):
        return self.url_externa or self.endpoint or "#"


class ConfiguracaoSistema(db.Model):
    __tablename__ = "configuracoes_sistema"

    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(80), nullable=False, unique=True, index=True)
    valor = db.Column(db.String(500), nullable=True)
    atualizada_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
