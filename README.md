# ML Price Hunter

Pipeline de monitoramento de preços em tempo real para o Mercado Livre, com alertas automáticos via Telegram quando ocorrem quedas de preço significativas.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                        projetos_shared (Docker Network)             │
│                                                                     │
│   ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐   │
│   │  n8n Cron    │────▶│  Mercado Livre   │     │  PostgreSQL  │   │
│   │  (agendador) │     │  API (externa)   │     │  :5432       │   │
│   └──────┬───────┘     └────────┬─────────┘     └──────▲───────┘   │
│          │                      │                       │           │
│          │              dados de preço                  │           │
│          │                      │                       │           │
│          │             ┌────────▼──────────┐            │           │
│          └────────────▶│  Python FastAPI   │────────────┘           │
│                        │  :8001            │  INSERT price_history  │
│                        └────────┬──────────┘                        │
│                                 │                                   │
│                    queda >= ALERT_THRESHOLD_PCT?                     │
│                                 │                                   │
│                        ┌────────▼──────────┐                        │
│                        │  n8n Telegram     │                        │
│                        │  Node (alerta)    │                        │
│                        └───────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

Fluxo resumido:

1. O **n8n Cron** dispara em intervalos configurados.
2. O nó **HTTP Request** consulta a API do Mercado Livre pelos produtos monitorados.
3. Os dados são enviados via **POST** ao serviço **Python FastAPI** (`/webhook/analyze`).
4. O FastAPI persiste o histórico de preços no **PostgreSQL** e retorna se deve ou não disparar alerta.
5. Caso a queda de preço atinja o limiar configurado (`ALERT_THRESHOLD_PCT`), o n8n aciona o nó **Telegram** e envia a notificação ao canal configurado.

---

## Pré-requisitos

Antes de subir este projeto, a infraestrutura compartilhada **deve estar em execução**:

```bash
cd ../infra
docker compose up -d
```

Isso garante que os seguintes serviços estejam disponíveis na rede `projetos_shared`:

| Serviço    | Host interno | Porta |
|------------|--------------|-------|
| PostgreSQL | `postgres`   | 5432  |
| n8n        | `n8n`        | 5678  |

> Consulte o README em `projetos/infra/` para detalhes sobre a configuração da infraestrutura compartilhada.

---

## Setup

### Passo 1 — Copiar o arquivo de variáveis de ambiente

```bash
cp .env.example .env
```

### Passo 2 — Preencher as credenciais no `.env`

Abra o arquivo `.env` e preencha os valores:

```dotenv
# PostgreSQL (infra compartilhada)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=nome_do_banco
POSTGRES_USER=usuario
POSTGRES_PASSWORD=sua_senha_aqui

# Alerta de preço
ALERT_THRESHOLD_PCT=5.0        # queda mínima em % para disparar alerta

# Telegram
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui

# FastAPI
API_PORT=8001
```

### Passo 3 — Subir o serviço Python

```bash
docker compose up --build -d
```

O serviço FastAPI ficará disponível em `http://localhost:8001`.

Para acompanhar os logs:

```bash
docker compose logs -f api
```

### Passo 4 — Importar o workflow no n8n

1. Acesse o n8n em `http://localhost:5678`.
2. No menu lateral, clique em **Workflows** → **Import from file**.
3. Selecione o arquivo `n8n/workflow.json` na raiz deste projeto.
4. Configure as credenciais do Telegram dentro do nó correspondente (veja a seção [Como configurar alertas](#como-configurar-alertas)).
5. Ative o workflow pelo toggle no canto superior direito.

---

## Como o workflow do n8n funciona

O arquivo `n8n/workflow.json` contém os seguintes nós, executados em sequência:

### 1. Cron — Agendador
- Tipo: `n8n-nodes-base.cron`
- Dispara o pipeline em intervalos regulares (padrão: a cada 15 minutos).
- Configurável diretamente na interface do n8n sem necessidade de alterar código.

### 2. Set — Definir produtos monitorados
- Tipo: `n8n-nodes-base.set`
- Define a lista de IDs de produtos do Mercado Livre a serem consultados (ex.: `MLB123456789`).
- Permite adicionar ou remover produtos sem tocar no código Python.

### 3. HTTP Request — Consultar API do Mercado Livre
- Tipo: `n8n-nodes-base.httpRequest`
- Realiza `GET` no endpoint público do Mercado Livre:
  ```
  https://api.mercadolivre.com.br/items/{item_id}
  ```
- Extrai os campos: `id`, `title`, `price`, `currency_id`, `permalink`.

### 4. HTTP Request — Enviar ao FastAPI
- Tipo: `n8n-nodes-base.httpRequest`
- Realiza `POST` para `http://api:8001/webhook/analyze` com o payload de preço atual.
- O FastAPI processa, persiste no banco e retorna `{ "alert": true/false, "drop_pct": float }`.

### 5. IF — Verificar se deve alertar
- Tipo: `n8n-nodes-base.if`
- Condição: `{{ $json.alert }} === true`
- Branch `true` → nó Telegram.
- Branch `false` → fluxo encerra silenciosamente.

### 6. Telegram — Enviar alerta
- Tipo: `n8n-nodes-base.telegram`
- Envia mensagem formatada ao chat configurado, incluindo:
  - Nome do produto
  - Preço anterior e preço atual
  - Percentual de queda
  - Link direto para o produto no Mercado Livre

---

## Esquema do banco de dados

Tabela `price_history` no PostgreSQL compartilhado:

```sql
CREATE TABLE IF NOT EXISTS price_history (
    id             SERIAL PRIMARY KEY,
    product_id     VARCHAR(50)    NOT NULL,
    product_title  TEXT           NOT NULL,
    price          NUMERIC(12, 2) NOT NULL,
    currency       VARCHAR(10)    NOT NULL DEFAULT 'BRL',
    permalink      TEXT,
    captured_at    TIMESTAMP      NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_history_product_id
    ON price_history (product_id);

CREATE INDEX IF NOT EXISTS idx_price_history_captured_at
    ON price_history (captured_at DESC);
```

| Coluna          | Tipo           | Descrição                                      |
|-----------------|----------------|------------------------------------------------|
| `id`            | SERIAL PK      | Identificador único autoincremental            |
| `product_id`    | VARCHAR(50)    | ID do produto no Mercado Livre (ex: MLB...)    |
| `product_title` | TEXT           | Título do produto no momento da captura        |
| `price`         | NUMERIC(12,2)  | Preço capturado                                |
| `currency`      | VARCHAR(10)    | Moeda (padrão: BRL)                            |
| `permalink`     | TEXT           | URL do anúncio no Mercado Livre                |
| `captured_at`   | TIMESTAMP      | Data/hora UTC da captura                       |

> A tabela é criada automaticamente pelo FastAPI na inicialização caso não exista.

---

## Endpoints da API

### `GET /health`

Verifica se o serviço está operacional e com conexão ativa ao banco.

**Request:**
```
GET http://localhost:8001/health
```

**Response `200 OK`:**
```json
{
  "status": "ok",
  "database": "connected"
}
```

---

### `POST /webhook/analyze`

Recebe os dados de preço de um produto, persiste no histórico e retorna se deve disparar alerta.

**Request:**
```
POST http://localhost:8001/webhook/analyze
Content-Type: application/json
```

```json
{
  "product_id": "MLB123456789",
  "product_title": "Notebook Lenovo IdeaPad 3 15ITL6",
  "price": 2799.99,
  "currency": "BRL",
  "permalink": "https://www.mercadolivre.com.br/p/MLB123456789"
}
```

**Response `200 OK` — sem alerta:**
```json
{
  "alert": false,
  "drop_pct": 1.2,
  "previous_price": 2834.00,
  "current_price": 2799.99,
  "product_id": "MLB123456789",
  "message": "Variação dentro do limiar configurado."
}
```

**Response `200 OK` — com alerta:**
```json
{
  "alert": true,
  "drop_pct": 8.5,
  "previous_price": 3060.00,
  "current_price": 2799.99,
  "product_id": "MLB123456789",
  "message": "Queda de preço detectada: 8.50% abaixo do último registro."
}
```

**Response `200 OK` — primeiro registro (sem histórico anterior):**
```json
{
  "alert": false,
  "drop_pct": null,
  "previous_price": null,
  "current_price": 2799.99,
  "product_id": "MLB123456789",
  "message": "Primeiro registro para este produto. Nenhum alerta disparado."
}
```

---

## Como configurar alertas

### Limiar de queda de preço (`ALERT_THRESHOLD_PCT`)

No arquivo `.env`, defina o percentual mínimo de queda de preço para que o alerta seja disparado:

```dotenv
ALERT_THRESHOLD_PCT=5.0   # alerta se o preço cair 5% ou mais em relação ao último registro
```

- Valor `5.0` significa: alerta quando o preço atual for pelo menos 5% menor que o último preço registrado.
- Aceita casas decimais (ex.: `2.5` para alertar a partir de 2,5% de queda).

### Configuração do bot Telegram

1. Crie um bot com o [@BotFather](https://t.me/botfather) no Telegram e copie o token gerado.
2. Obtenha seu `chat_id`:
   - Envie uma mensagem para o bot.
   - Acesse: `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   - Localize o campo `"chat": { "id": XXXXXXX }`.
3. Preencha no `.env`:
   ```dotenv
   TELEGRAM_BOT_TOKEN=123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ
   TELEGRAM_CHAT_ID=-1001234567890
   ```
4. No workflow do n8n, abra o nó **Telegram** e selecione a credencial cadastrada com o token acima.

> Para alertas em grupos, adicione o bot ao grupo e use o `chat_id` negativo do grupo.

---

## Notas de engenharia

### Idempotência — sem duplicatas no mesmo minuto

O serviço FastAPI utiliza uma estratégia de **SELECT antes do INSERT** para evitar registros duplicados quando o mesmo produto é consultado mais de uma vez no mesmo minuto:

```python
# Pseudocódigo da lógica de idempotência
existing = db.execute(
    "SELECT id FROM price_history "
    "WHERE product_id = %s "
    "AND date_trunc('minute', captured_at) = date_trunc('minute', NOW())",
    (product_id,)
).fetchone()

if not existing:
    db.execute("INSERT INTO price_history (...) VALUES (...)")
```

Isso garante que, mesmo que o n8n dispare o webhook mais de uma vez no mesmo minuto (ex.: por retry ou falha temporária), apenas um registro por produto por minuto será gravado no banco.

### Tratamento de erros

- Cada item processado é envolvido em um bloco `try-except` independente, garantindo que a falha em um produto não interrompa o processamento dos demais.
- Em caso de erro na transação com o banco, um `rollback` é executado explicitamente antes de relançar a exceção, evitando estados inconsistentes.
- Erros são logados com o stack trace completo para facilitar diagnóstico.

```
[produto MLB999] ERRO ao processar: connection timeout
→ rollback executado
→ demais produtos continuam sendo processados
```

### Como estender o projeto

| Objetivo                              | Onde modificar                              |
|---------------------------------------|---------------------------------------------|
| Adicionar novos produtos monitorados  | Nó **Set** no workflow do n8n               |
| Monitorar outro marketplace           | Substituir o nó HTTP Request do n8n         |
| Alterar canal de alerta (ex.: Slack)  | Substituir o nó Telegram no workflow        |
| Adicionar novos campos ao histórico   | Migrar tabela + atualizar modelo Pydantic   |
| Criar dashboard de preços             | Conectar BI (Metabase, Grafana) ao PostgreSQL |
| Aumentar frequência de coleta         | Ajustar expressão cron no nó agendador      |

---

## Estrutura do projeto

```
realtime-ecommerce-alert-pipeline/
│
├── api/                          # Serviço Python FastAPI
│   ├── main.py                   # Entrypoint: rotas /health e /webhook/analyze
│   ├── database.py               # Conexão e helpers PostgreSQL
│   ├── models.py                 # Schemas Pydantic (request/response)
│   ├── alert.py                  # Lógica de cálculo de queda de preço
│   └── requirements.txt          # Dependências Python
│
├── n8n/
│   └── workflow.json             # Workflow n8n exportado (importar via UI)
│
├── docker-compose.yml            # Sobe apenas o serviço FastAPI
│                                 # (PostgreSQL e n8n vêm da infra/)
│
├── .env.example                  # Modelo de variáveis de ambiente
├── .env                          # Variáveis locais (não versionar)
└── README.md                     # Este arquivo
```

> **Nota:** O `docker-compose.yml` deste projeto **não** sobe PostgreSQL nem n8n. Esses serviços são fornecidos pela infraestrutura compartilhada em `projetos/infra/`. A rede `projetos_shared` deve existir antes de executar `docker compose up`.

---

## Dependências externas

| Dependência          | Versão recomendada | Finalidade                          |
|----------------------|--------------------|-------------------------------------|
| Python               | 3.11+              | Runtime do FastAPI                  |
| FastAPI              | 0.111+             | Framework web assíncrono            |
| psycopg2-binary      | 2.9+               | Driver PostgreSQL                   |
| pydantic             | 2.x                | Validação de schemas                |
| uvicorn              | 0.29+              | Servidor ASGI                       |
| Docker               | 24+                | Containerização                     |
| Docker Compose       | v2                 | Orquestração local                  |
| n8n                  | via infra/         | Orquestração do workflow            |
| PostgreSQL           | 16 (via infra/)    | Persistência do histórico de preços |
