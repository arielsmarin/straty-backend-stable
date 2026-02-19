# Panoconfig360 Totem

Sistema de configuração e visualização de panoramas 360° com renderização progressiva de tiles.

## Visão Geral

Este projeto implementa um configurador interativo de ambientes 360° que permite:

- Seleção dinâmica de materiais e acabamentos
- Renderização progressiva de panoramas em alta qualidade
- Visualização imediata com carregamento otimizado de tiles
- Sistema de cache inteligente para melhor performance

## Arquitetura

### Backend (Python/FastAPI)
- **`panoconfig360_backend/`**: API de renderização e gerenciamento de tiles
  - Renderização em 2 fases (LOD baixo + LOD alto em background)
  - Sistema de eventos para notificação de tiles prontos
  - Cache local de tiles gerados

### Frontend (Vanilla JS + Marzipano)
- **`panoconfig360_frontend/`**: Aplicação web para visualização 360°
  - Carregamento progressivo de tiles
  - Sistema de cache-busting com parâmetros `?v=`
  - Polling de eventos para atualização de qualidade em tempo real

### CRUD App
- **`simple_crud_app/`**: Interface de gerenciamento de configurações
  - Gestão de clientes, cenas, layers e materiais
  - Exportação de configuração em JSON

## 🚀 Production Deployment

**Complete deployment guide for production environments:**

👉 **[docs/DEPLOYMENT_MASTER.md](docs/DEPLOYMENT_MASTER.md)** - Start here!

**Architecture**: Serverless, globally distributed, cost-optimized
- **Backend**: Render.com (FastAPI)
- **Frontend**: Cloudflare Pages (Static)
- **Storage**: Cloudflare R2 (Zero egress fees)
- **CDN**: Cloudflare (200+ global POPs)

**Estimated cost**: $8-30/month depending on traffic

**Key features**:
- ✅ Global CDN with 95%+ cache hit ratio
- ✅ Auto-scaling backend
- ✅ Zero-downtime deploys
- ✅ Production hardening (rate limiting, CORS, security)
- ✅ Comprehensive monitoring and testing

**Quick links**:
- [Architecture Overview](docs/DEPLOYMENT_ARCHITECTURE.md)
- [Backend Setup (Render)](docs/DEPLOYMENT_RENDER.md)
- [Storage Setup (R2)](docs/DEPLOYMENT_R2.md)
- [Frontend Setup (Pages)](docs/DEPLOYMENT_CLOUDFLARE_PAGES.md)
- [Performance Testing](docs/DEPLOYMENT_PERFORMANCE.md)

## Documentação Técnica

### 📖 Parâmetros de URL dos Tiles (`?v=`)

Uma das perguntas mais comuns é: **"O que significa `?v=0` e `?v=1` nos links dos tiles?"**

Esta funcionalidade implementa um sistema de **carregamento progressivo** que:

1. Carrega tiles de baixa qualidade imediatamente (LOD 0/1)
2. Renderiza tiles de alta qualidade em background (LOD 2+)
3. Atualiza progressivamente a visualização sem recarregar a página

Para entender completamente como funciona o sistema de parâmetros `?v=`, consulte:

👉 **[docs/TILE_PARAMETERS.md](docs/TILE_PARAMETERS.md)**

Este documento explica em detalhes:
- Como funciona o cache-busting com `?v=`
- Workflow de renderização progressiva (2 fases)
- Sistema de polling de eventos de tiles
- Estrutura de dados e configurações
- Troubleshooting e otimizações

## Estrutura do Projeto

```
panoconfig360_totem/
├── docs/                           # Documentação técnica
│   ├── TILE_PARAMETERS.md          # Explicação do sistema ?v=
│   └── TILE_FADE_TRANSITION.md     # Sistema de transição LOD
├── panoconfig360_backend/          # API Backend (FastAPI)
│   ├── api/
│   │   └── server.py              # Endpoints principais
│   ├── render/
│   │   ├── dynamic_stack.py       # Composição de layers
│   │   └── split_faces_cubemap.py # Geração de tiles do cubemap
│   ├── storage/
│   │   ├── storage_local.py       # Storage em disco
│   │   └── tile_upload_queue.py   # Fila de upload de tiles
│   └── tests/
├── panoconfig360_frontend/         # Frontend (Vanilla JS)
│   ├── js/
│   │   ├── viewer/
│   │   │   └── ViewerManager.js   # Gerenciamento de tiles e ?v=
│   │   ├── ui/
│   │   └── core/
│   ├── css/
│   └── index.html
├── panoconfig360_cache/            # Cache local de tiles gerados
│   └── clients/{client_id}/
│       └── cubemap/{scene_id}/
│           └── tiles/{build}/      # Tiles organizados por build
└── simple_crud_app/                # CRUD de configuração
    ├── backend/
    └── frontend/
```

## Quick Start

### Backend

```bash
cd panoconfig360_backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn panoconfig360_backend.api.server:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

O frontend é servido automaticamente pelo backend FastAPI em:
- **Aplicação**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### CRUD App (Opcional)

```bash
cd simple_crud_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8001
```

## Endpoints Principais

### Renderização de Panoramas

```http
POST /api/render
Content-Type: application/json

{
  "client": "cliente-id",
  "scene": "cena-id",
  "selection": {
    "layer1": "material1",
    "layer2": "material2"
  }
}
```

**Resposta:**
```json
{
  "status": "generated",
  "build": "abc123",
  "tiles": {
    "baseUrl": "/panoconfig360_cache",
    "tileRoot": "clients/cliente-id/cubemap/cena-id/tiles/abc123",
    "pattern": "abc123_{f}_{z}_{x}_{y}.jpg",
    "build": "abc123"
  }
}
```

### Eventos de Tiles (Polling)

```http
GET /api/render/events?tile_root={tileRoot}&cursor={cursor}&limit=300
```

**Resposta:**
```json
{
  "status": "success",
  "data": {
    "events": [...],
    "cursor": 150,
    "hasMore": false,
    "completed": true
  }
}
```

## Funcionalidades Principais

### 1. Renderização Progressiva (3 Fases)

- **Fase 1 (Síncrona)**: Gera LOD 0 em ~1-2 segundos
  - Usuário vê panorama imediatamente
  - Qualidade inicial para navegação rápida

- **Fase 2 (Background)**: Gera LOD 1 progressivamente
  - Tiles de resolução média gerados em background
  - Frontend é notificado via polling de eventos
  - Qualidade melhora gradualmente

- **Fase 3 (Background)**: Gera LOD 2+ progressivamente
  - Tiles de alta resolução gerados em background
  - Frontend é notificado via polling de eventos
  - Qualidade melhora gradualmente até alta resolução

### 2. Sistema de Cache Inteligente

- Tiles têm cache HTTP de 1 ano (`immutable`)
- Parâmetro `?v=` permite atualização sem limpar cache
- Build string determinística evita regeneração

### 3. Otimizações de Performance

- **Rate limiting**: 1 segundo entre requisições
- **Concorrência**: 8 tiles carregados simultaneamente
- **Fast retry**: Retry automático em 150ms
- **Workers**: 4 threads de upload de tiles

## Cache e Storage

### Estrutura de Cache Local

```
panoconfig360_cache/
└── clients/
    └── {client-id}/
        └── cubemap/
            └── {scene-id}/
                └── tiles/
                    └── {build}/
                        ├── {build}_f_0_0_0.jpg    # Front, LOD 0
                        ├── {build}_f_1_0_0.jpg    # Front, LOD 1
                        ├── {build}_f_2_0_0.jpg    # Front, LOD 2
                        ├── metadata.json          # Metadados do render
                        └── tile_events.ndjson     # Log de eventos
```

### Build String

Cada combinação única de materiais gera uma build string determinística em base36:

```python
# Algoritmo em panoconfig360_backend/render/dynamic_stack.py
# Função: build_string_from_selection() (aproximadamente linhas 101-129)

# Formato: [scene_index:2][layer0:2][layer1:2][layer2:2][layer3:2][layer4:2]
# Total: 12 caracteres em base36 (0-9, a-z)

# Exemplo:
# Scene 1, materiais [5, 10, 3, 0, 7] → "01050a03000z"
```

**Componentes:**
- **2 chars**: Índice da cena (00-zz em base36)
- **10 chars**: 5 layers × 2 chars cada (índice do material selecionado)

**Benefícios:**
- Reuso de cache para mesmas seleções
- Identificação única de cada configuração
- URLs previsíveis e cacheáveis
- String compacta (12 chars vs hash longo)

## Tecnologias Utilizadas

### Backend
- **FastAPI**: Framework web moderno e rápido
- **Pillow/PIL**: Processamento de imagens
- **VIPS** (opcional): Processamento de imagens de alta performance

### Frontend
- **Marzipano**: Biblioteca para visualização de panoramas 360°
- **Vanilla JavaScript**: Sem frameworks, código leve e rápido

### Storage
- **Local File System**: Cache em disco para desenvolvimento
- **S3-compatible** (futuro): Suporte a storage em nuvem

## Desenvolvimento

### Estrutura de Commits

Use mensagens descritivas:
```bash
git commit -m "feat: adiciona suporte a LOD 3"
git commit -m "fix: corrige polling de eventos"
git commit -m "docs: atualiza documentação de tiles"
```

### Testes

```bash
# Backend
cd panoconfig360_backend
pytest

# CRUD App
cd simple_crud_app
pytest tests/
```

## Troubleshooting

### Tiles não carregam?

1. Verifique se o backend está rodando
2. Verifique o console do browser para erros
3. Verifique se os tiles foram gerados em `panoconfig360_cache/`

### Qualidade não melhora?

1. Verifique os logs do backend para erros no background render
2. Verifique o polling de eventos no Network tab
3. Consulte [docs/TILE_PARAMETERS.md](docs/TILE_PARAMETERS.md#troubleshooting)

### Cache persistente?

- O parâmetro `?v=` força nova requisição
- Limpe o cache do browser se necessário
- Desabilite cache no DevTools durante desenvolvimento

## Contribuindo

1. Faça fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -am 'feat: adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## Licença

[Especificar licença do projeto]

## Suporte

Para dúvidas sobre funcionalidades específicas:
- **Parâmetros de URL dos tiles (`?v=`)**: Ver [docs/TILE_PARAMETERS.md](docs/TILE_PARAMETERS.md)
- **Transições LOD**: Ver [docs/TILE_FADE_TRANSITION.md](docs/TILE_FADE_TRANSITION.md)
- **CRUD de configuração**: Ver [simple_crud_app/README.md](simple_crud_app/README.md)
