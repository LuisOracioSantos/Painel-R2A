# Meu Painel Flask

Painel central de aplicacoes criado com Flask, Application Factory, Blueprints,
autenticacao, controle de acesso e banco SQLite via ORM.

## Estrutura

```text
meu_painel_flask/
|-- apps/
|   |-- __init__.py                 # Application Factory e registro geral
|   |-- comum/                      # Infraestrutura compartilhada
|   |   |-- extensoes.py             # SQLAlchemy, LoginManager
|   |   |-- modelos.py               # Entidades e relacionamentos
|   |   |-- seguranca.py             # CSRF, decorators e login helpers
|   |   |-- static/
|   |   |   `-- css/
|   |   |       `-- base.css          # CSS compartilhado do layout
|   |   `-- servicos/
|   |       `-- inicializacao.py      # Seed e criacao inicial do banco
|   |-- autenticacao/
|   |   |-- routes.py                # Rotas de login/logout
|   |   |-- servicos.py              # Regras de autenticacao
|   |   |-- static/
|   |   |   `-- css/
|   |   |       `-- autenticacao.css
|   |   `-- templates/
|   |       `-- autenticacao/
|   |           `-- login.html
|   |-- dashboard/
|   |   |-- routes.py                # Rotas do admin
|   |   |-- servicos.py              # Regras de usuarios, apps e permissoes
|   |   |-- static/
|   |   |   `-- css/
|   |   |       `-- dashboard.css
|   |   `-- templates/
|   |       `-- dashboard/
|   |           `-- index.html
|   |-- cadastromapa/
|   |   |-- routes.py                # Tela e API de importacao do mapa
|   |   |-- servicos.py              # Leitura e parse do PDF
|   |   |-- static/
|   |   |   |-- css/
|   |   |   |   `-- cadastromapa.css
|   |   |   `-- js/
|   |   |       `-- cadastromapa.js
|   |   `-- templates/
|   |       `-- cadastromapa/
|   |           `-- index.html
|   `-- painel_principal/
|       |-- routes.py                # Rotas do painel do usuario
|       |-- servicos.py              # Consulta e montagem dos cards
|       |-- static/
|       |   `-- css/
|       |       `-- painel_principal.css
|       `-- templates/
|           `-- painel_principal/
|               `-- index.html
|-- templates/
|   |-- base.html
|   `-- erros/
|       |-- 400.html
|       |-- 403.html
|       `-- 404.html
|-- .env
|-- config.py
|-- requirements.txt
`-- wsgi.py
```

## Como Executar

```powershell
cd meu_painel_flask
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
flask run
```

Depois acesse `http://127.0.0.1:5000`.

Se a porta `5000` ja estiver ocupada:

```powershell
flask --app wsgi:app run --port 5055
```

## Como Executar Com Docker

Crie o arquivo `.env` a partir do exemplo e ajuste principalmente `SECRET_KEY`,
`ADMIN_PADRAO_EMAIL` e `ADMIN_PADRAO_SENHA`.

```powershell
copy .env.example .env
docker compose up -d --build
```

Depois acesse `http://127.0.0.1:8000`.

Dados persistentes ficam montados no host:

- `instance/`: banco SQLite e arquivos temporarios da aplicacao.
- `static/uploads/`: logos e icones enviados pelo painel.

Para ver logs:

```powershell
docker compose logs -f
```

Para parar:

```powershell
docker compose down
```

## Acessos Iniciais

O banco e os dados iniciais sao criados automaticamente em desenvolvimento.

```text
E-mail: admin@local
Senha: Admin@12345
```

Altere esses valores no `.env` antes de usar fora do ambiente local.

## Rotas Principais

- `/auth/login`: autenticacao.
- `/`: painel principal do usuario.
- `/painel`: alias do painel principal.
- `/admin/`: dashboard administrativo de configuracoes.
- `/cadastromapa/`: importacao de PDF do Cadastro Mapa.

## Organizacao Por Aplicacao

Cada aplicacao segue o mesmo desenho:

- `routes.py`: somente rotas, flash, redirect e renderizacao.
- `servicos.py`: regras de negocio, consultas e preparacao de dados.
- `static/css/`: estilos especificos da aplicacao.
- `static/js/`: scripts especificos da aplicacao, quando existir.
- `templates/<nome_app>/`: telas do blueprint.
- `__init__.py`: exportacao do blueprint.

Codigo compartilhado fica em `apps/comum`, incluindo o CSS base do layout,
evitando dependencias circulares e mantendo os blueprints independentes.

## Seguranca E Desempenho

- Senhas sao armazenadas com hash do Werkzeug.
- Formularios POST usam token CSRF em sessao.
- Apenas usuarios com perfil `admin` acessam `/admin/`.
- Consultas usam SQLAlchemy ORM, indices em campos de busca e relacionamento muitos-para-muitos para permissoes.
- Cookies de sessao usam `HttpOnly` e `SameSite=Lax`.

## Como Adicionar Uma Nova Aplicacao

1. Crie uma pasta dentro de `apps/`, seguindo o padrao do `painel_principal` ou `dashboard`.
2. Defina o `Blueprint` no arquivo `routes.py`.
3. Coloque regras de negocio e consultas em `servicos.py`.
4. Registre o blueprint em `registrar_blueprints()` no arquivo `apps/__init__.py`.
5. Cadastre a aplicacao no dashboard administrativo e defina quais usuarios terao acesso.
