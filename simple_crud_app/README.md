# Panoconfig360 - CRUD de Configuração por Tenant (FastAPI + Vanilla JS)

Este módulo implementa um CRUD alinhado à dinâmica do configurador:

- **Cliente (tenant)** → possui várias **cenas** (`scene_index`)
- Cada cena possui **3 ou 4 layers**
- Cada layer possui vários **materiais** (quantidade variável)
- Itens armazenam caminhos relativos de assets (`mask`, `file`, `thumbnail`)
- Saída final em JSON semelhante ao `monte-negro_cfg.json`

## Estrutura

```text
simple_crud_app/
├── backend/
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── routes/config_routes.py
│   ├── services/config_service.py
│   ├── repositories/config_repository.py
│   ├── storage/file_storage.py
│   └── utils/build.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/
│   ├── test_build_utils.py
│   └── test_config_service.py
└── requirements.txt
```

## Regras de domínio aplicadas

- Resposta padronizada: `{ "status": "success|error", "data": ..., "error": ... }`
- Header obrigatório `X-Tenant-ID` para operações por tenant.
- `client_id` sempre validado contra tenant do header.
- Paths de assets **apenas relativos** (sem caminho absoluto).
- Lock por chave de tenant na exportação (`tenant:cfg`) para evitar concorrência duplicada.
- Build string determinística em base36 (`backend/utils/build.py`).

## Rodando

```bash
cd simple_crud_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

- Frontend: `http://127.0.0.1:8000/`
- Docs API: `http://127.0.0.1:8000/docs`

## Endpoints principais

- `POST /api/clients`
- `PUT /api/clients/{client_id}`
- `POST /api/clients/{client_id}/scenes`
- `POST /api/scenes/{scene_id}/layers`
- `POST /api/layers/{layer_id}/materials`
- `GET /api/clients/{client_id}/config`
- `GET /api/builds/{build}/validate`

## Observação de base de código

Este CRUD continua sendo um módulo novo em `simple_crud_app/`, sem reuso direto das rotas/render atuais de `panoconfig360_backend`.
