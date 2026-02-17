# Parâmetros de URL dos Tiles (`?v=`)

## O que significa `?v=0` e `?v=1` nos links dos tiles?

O parâmetro `?v=` nas URLs dos tiles é um **cache-busting parameter** (parâmetro de quebra de cache) utilizado para implementar o sistema de **progressive tile loading** (carregamento progressivo de tiles).

## Como Funciona

### 1. Sistema de Revisão de Tiles

Cada tile no panorama 360° possui um número de revisão que é incrementado quando uma nova versão do tile fica disponível:

```javascript
// ViewerManager.js, linha 22
this._tileRevisionMap = new Map();
```

### 2. Construção da URL do Tile

Quando um tile é carregado, sua URL é construída com o parâmetro `?v=` seguido do número de revisão:

```javascript
// ViewerManager.js, linha 56
const url = `${baseUrl}/${tiles.build}_${tile.face}_${tile.z}_${tile.x}_${tile.y}.jpg?v=${rev}`;
```

**Exemplos:**
- Primeira carga: `12abc_f_0_0_0.jpg?v=0`
- Após atualização: `12abc_f_0_0_0.jpg?v=1`
- Segunda atualização: `12abc_f_0_0_0.jpg?v=2`

### 3. Workflow de Renderização Progressiva

O sistema utiliza um processo de renderização em 2 fases:

#### **Fase 1: LOD 0 e LOD 1 (Resposta Imediata)**
- O servidor gera apenas os tiles de baixa resolução (LOD 0 e LOD 1)
- Resposta rápida (~2-3 segundos)
- Tiles são servidos com `?v=0`
- Usuário vê o panorama imediatamente, mas com qualidade média

#### **Fase 2: LODs Superiores (Background)**
- Processamento continua em background
- Tiles de alta resolução (LOD 2+) são gerados gradualmente
- Backend envia eventos via `/api/render/events`
- Frontend detecta novos tiles disponíveis
- `forceTileRefresh()` é chamado para incrementar a revisão
- Browser recarrega o tile com `?v=1`, ignorando o cache
- Usuário vê gradualmente a qualidade melhorando

### 4. Polling de Eventos de Tiles

O frontend monitora continuamente o status dos tiles:

```javascript
// ViewerManager.js, linhas 71-126
_scheduleTileEventPolling(tiles) {
  // Polling a cada 150ms
  // Busca eventos de novos tiles prontos
  // Chama forceTileRefresh() para cada tile atualizado
}
```

**Endpoint consultado:**
```
GET /api/render/events?tile_root={tileRoot}&cursor={cursor}&limit=300
```

**Resposta:**
```json
{
  "status": "success",
  "data": {
    "events": [
      {
        "filename": "12abc_f_2_0_0.jpg",
        "build": "12abc",
        "state": "visible",
        "lod": 2,
        "ts": 1708131234567
      }
    ],
    "cursor": 150,
    "hasMore": false,
    "completed": true
  }
}
```

## Benefícios desta Abordagem

### ✅ Experiência do Usuário
- **Resposta imediata**: Usuário vê o panorama em poucos segundos
- **Melhoria progressiva**: Qualidade melhora gradualmente sem recarregar a página
- **Sem loading infinito**: Sistema não bloqueia esperando alta resolução

### ✅ Performance
- **Cache eficiente**: Browser cacheia tiles de alta qualidade permanentemente
- **Sem desperdício**: Apenas tiles visíveis são priorizados
- **Concorrência controlada**: 8 tiles carregados simultaneamente (linha 45)

### ✅ Otimização de Servidor
- **Rate limiting**: Previne sobrecarga (1 segundo entre requisições)
- **Processing distribuído**: LODs gerados em fases
- **Fast retry**: Recarregamento rápido em caso de falha (150ms delay)

## Fluxo Completo de Atualização

```
1. Usuário seleciona materiais
   ↓
2. Frontend faz POST /api/render
   ↓
3. Backend gera LOD 0+1 (rápido)
   ↓
4. Backend retorna tiles com build={hash}
   ↓
5. Frontend carrega tiles com ?v=0
   ↓
6. Frontend inicia polling de eventos
   ↓
7. Backend gera LOD 2+ em background
   ↓
8. Backend escreve eventos em tile_events.ndjson
   ↓
9. Frontend recebe eventos via /api/render/events
   ↓
10. Frontend chama forceTileRefresh(face, level, x, y)
    ↓
11. Revisão incrementada: ?v=0 → ?v=1
    ↓
12. Browser recarrega tile (ignora cache)
    ↓
13. Usuário vê melhoria gradual de qualidade
```

## Estrutura de Dados

### TileRevisionMap
```javascript
Map {
  "f:0:0:0" => 0,   // LOD 0, ainda não atualizado
  "f:1:0:0" => 0,   // LOD 1, ainda não atualizado
  "f:2:0:0" => 1,   // LOD 2, já atualizado uma vez
  "t:0:0:0" => 0,   // Face top, LOD 0
  // ...
}
```

### Faces do Cubemap
- `f` - front (frente)
- `b` - back (trás)
- `l` - left (esquerda)
- `r` - right (direita)
- `t` - top (topo)
- `d` - down (baixo)

### Níveis de LOD (Level of Detail)
- **LOD 0**: 512×512px (fallback)
- **LOD 1**: 1024×1024px (resolução inicial)
- **LOD 2**: 2048×2048px (alta resolução)

## Configuração no Código

### ViewerManager (Frontend)
```javascript
// Intervalo de polling
const pollInterval = 150; // ms (linha 122)

// Concorrência de download
const concurrency = 8; // tiles simultâneos (linha 60)

// Delay de retry
const retryDelay = 150; // ms (linha 59)
```

### Server (Backend)
```javascript
// Rate limiting
const MIN_INTERVAL = 1.0; // segundos

// Tamanho dos tiles
const TILE_SIZE = 512; // pixels

// Workers de upload
const UPLOAD_WORKERS = 4;
```

## Cache Control

Os tiles têm cache HTTP configurado para duração máxima:

```http
Cache-Control: public, max-age=31536000, immutable
```

Isso significa:
- **max-age=31536000**: Cache válido por 1 ano
- **immutable**: Conteúdo nunca muda para essa URL
- **Importante**: Por isso o `?v=` é necessário - altera a URL para forçar nova requisição

## Troubleshooting

### Tiles não estão atualizando?
1. Verifique o console: `[POI Capture] ativado` deve aparecer
2. Verifique Network tab: polling de `/api/render/events` deve estar ativo
3. Verifique se eventos estão sendo recebidos com `state: "visible"`

### Qualidade não melhora?
1. Verifique se o backend completou a renderização (`completed: true`)
2. Verifique se os tiles LOD 2+ foram gerados no servidor
3. Verifique logs do backend para erros no background task

### Cache persistente?
1. O parâmetro `?v=` força nova requisição mesmo com cache
2. Se necessário, limpe o cache do browser manualmente
3. Desabilite cache no DevTools durante desenvolvimento

## Referências no Código

- **Frontend**: `panoconfig360_frontend/js/viewer/ViewerManager.js`
  - Linhas 19-22: Sistema de revisão de tiles (comentário e propriedade)
  - Linhas 50-61: Criação de URL source com `?v=` e configurações
  - Linhas 71-126: Polling de eventos e atualização

- **Backend**: `panoconfig360_backend/api/server.py`
  - Linhas 76-91: Writer de eventos de estado de tiles
  - Linhas 212-418: Endpoint `/api/render` (2 fases)
  - Linhas 421-453: Endpoint `/api/render/events`
